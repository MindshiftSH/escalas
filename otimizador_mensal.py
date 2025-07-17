from models import db, Escala, Funcionario, Turno, Configuracao, Restricao
from datetime import datetime, timedelta
from escalonador import gerar_escala_ortools
from ortools.sat.python import cp_model
import json
import random
from collections import defaultdict
from flask import current_app

def get_app_context():
    """Obtém o contexto da aplicação Flask"""
    try:
        return current_app.app_context()
    except RuntimeError:
        # Se não há contexto ativo, criar um contexto de teste
        from app import app
        return app.app_context()

class OtimizadorMensal:
    def __init__(self, mes, ano, valencia):
        self.mes = mes
        self.ano = ano
        self.valencia = valencia
        self.funcionarios = []
        self.turnos = []
        self.config = None
        self.dias = []
        self.restricoes = {}
        self.perfil_ideal = None
        
    def carregar_dados(self):
        """Carrega todos os dados necessários"""
        with get_app_context():
            self.funcionarios = Funcionario.query.filter_by(valencia=self.valencia, ativo=True).all()
            self.turnos = Turno.query.filter_by(valencia=self.valencia).all()
            self.config = Configuracao.query.filter_by(valencia=self.valencia).first()
            
            # Preparar dias do mês
            data_inicio = datetime(self.ano, self.mes, 1)
            if self.mes == 12:
                data_fim = datetime(self.ano + 1, 1, 1) - timedelta(days=1)
            else:
                data_fim = datetime(self.ano, self.mes + 1, 1) - timedelta(days=1)
            
            # Filtrar apenas dias de funcionamento
            self.dias = self.filtrar_dias_funcionamento(data_inicio, data_fim)
            
            # Aplicar rodízio automático se configurado
            if self.config and self.config.ativar_rodizio:
                self.aplicar_rodizio_automatico()
            
            # Carregar perfil ideal se existir
            try:
                with open('Treino/perfil_ideal.json', 'r', encoding='utf-8') as f:
                    perfil_ideal_raw = json.load(f)
                # Mapear nomes do perfil para IDs reais
                nome_para_id = {f.nome: f.id for f in self.funcionarios}
                self.perfil_ideal = {}
                for nome, contagem in perfil_ideal_raw.items():
                    if nome in nome_para_id:
                        self.perfil_ideal[nome_para_id[nome]] = contagem
            except Exception as e:
                self.perfil_ideal = None
    
    def filtrar_dias_funcionamento(self, data_inicio, data_fim):
        """Filtra apenas os dias de funcionamento baseado na configuração"""
        dias_funcionamento = []
        
        if self.config and self.config.dias_funcionamento:
            try:
                dias_config = json.loads(self.config.dias_funcionamento)
                print(f"Dias de funcionamento configurados: {dias_config}")
                
                # Mapear dias da semana
                dias_semana = {
                    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
                    'friday': 4, 'saturday': 5, 'sunday': 6
                }
                
                dias_habilitados = set()
                for dia in dias_config:
                    if dia in dias_semana:
                        dias_habilitados.add(dias_semana[dia])
                
                print(f"Dias habilitados (0=Segunda, 6=Domingo): {dias_habilitados}")
                
                # Filtrar apenas dias de funcionamento
                data_atual = data_inicio
                while data_atual <= data_fim:
                    if data_atual.weekday() in dias_habilitados:
                        dias_funcionamento.append(data_atual.date())
                    data_atual += timedelta(days=1)
                
                print(f"Total de dias de funcionamento no mês: {len(dias_funcionamento)}")
                
            except Exception as e:
                print(f"Erro ao filtrar dias de funcionamento: {e}")
                # Se houver erro, incluir todos os dias
                data_atual = data_inicio
                while data_atual <= data_fim:
                    dias_funcionamento.append(data_atual.date())
                    data_atual += timedelta(days=1)
        else:
            # Se não há configuração, incluir todos os dias
            print("⚠️  Nenhuma configuração de dias de funcionamento encontrada. Incluindo todos os dias.")
            data_atual = data_inicio
            while data_atual <= data_fim:
                dias_funcionamento.append(data_atual.date())
                data_atual += timedelta(days=1)
        
        return dias_funcionamento
    
    def aplicar_rodizio_automatico(self):
        """Aplica rodízio automático criando restrições de folga"""
        if not self.config.ativar_rodizio or not self.config.data_inicio_rodizio or not self.config.padrao_rodizio:
            print("❌ Rodízio não configurado ou dados incompletos")
            return
        
        try:
            padrao_personalizado = json.loads(self.config.padrao_rodizio)
        except Exception as e:
            print(f"❌ Erro ao carregar padrão de rodízio: {e}")
            return
        
        print(f"✅ Aplicando rodízio automático...")
        print(f"Padrão: {padrao_personalizado}")
        
        # Calcular ciclo total
        ciclo_total = sum(periodo['dias'] for periodo in padrao_personalizado)
        print(f"Ciclo total: {ciclo_total} dias")
        
        # Aplicar padrão personalizado para todos os funcionários
        funcionarios_com_rodizio = 0
        for funcionario in self.funcionarios:
            # Calcular offset baseado no ID do funcionário para distribuir o início do ciclo
            offset_funcionario = funcionario.id % len(self.funcionarios)
            
            folgas_funcionario = 0
            for dia in self.dias:  # Usar apenas dias de funcionamento
                # Calcular posição no ciclo personalizado
                dias_desde_inicio = (dia - self.config.data_inicio_rodizio).days
                posicao_ciclo = (dias_desde_inicio + offset_funcionario) % ciclo_total
                
                # Determinar se está em período de folga
                posicao_acumulada = 0
                em_folga = False
                
                for periodo in padrao_personalizado:
                    if posicao_ciclo < posicao_acumulada + periodo['dias']:
                        em_folga = (periodo['tipo'] == 'folga')
                        break
                    posicao_acumulada += periodo['dias']
                
                # Se está em folga, adicionar à restrição
                if em_folga:
                    if funcionario.id not in self.restricoes:
                        self.restricoes[funcionario.id] = set()
                    self.restricoes[funcionario.id].add(dia)
                    folgas_funcionario += 1
            
            if folgas_funcionario > 0:
                funcionarios_com_rodizio += 1
                print(f"  {funcionario.nome}: {folgas_funcionario} folgas aplicadas")
        
        print(f"✅ Rodízio aplicado para {funcionarios_com_rodizio}/{len(self.funcionarios)} funcionários")
        
        # Verificar se há funcionários suficientes para preencher todos os turnos
        self.verificar_e_ajustar_viabilidade()
    
    def verificar_e_ajustar_viabilidade(self):
        """Verifica se há funcionários suficientes e ajusta folgas se necessário"""
        # Calcular quantos funcionários precisamos por dia
        funcionarios_por_dia = {}
        for dia in self.dias:
            funcionarios_por_dia[dia] = sum(turno.funcionarios_necessarios for turno in self.turnos)
        
        # Calcular total de funcionários necessários no mês
        total_turnos_necessarios = sum(funcionarios_por_dia.values())
        
        # Calcular funcionários disponíveis
        total_funcionarios_disponiveis = 0
        for funcionario in self.funcionarios:
            folgas_funcionario = len(self.restricoes.get(funcionario.id, set()))
            dias_disponiveis = len(self.dias) - folgas_funcionario
            total_funcionarios_disponiveis += dias_disponiveis
        
        print(f"Total turnos necessários: {total_turnos_necessarios}")
        print(f"Total funcionários disponíveis: {total_funcionarios_disponiveis}")
        
        if total_funcionarios_disponiveis < total_turnos_necessarios:
            print(f"⚠️  AVISO: Pode não ser possível preencher todos os turnos!")
            print(f"   Necessários: {total_turnos_necessarios}")
            print(f"   Disponíveis: {total_funcionarios_disponiveis}")
            print(f"   Diferença: {total_turnos_necessarios - total_funcionarios_disponiveis}")
            
            # Se não há funcionários suficientes, reduzir as folgas para garantir preenchimento
            print("🔄 Ajustando folgas para garantir preenchimento dos turnos...")
            self.ajustar_folgas_para_preenchimento(funcionarios_por_dia)
    
    def ajustar_folgas_para_preenchimento(self, funcionarios_por_dia):
        """Ajusta as folgas para garantir que haja funcionários suficientes para preencher todos os turnos"""
        # Calcular quantos dias de folga cada funcionário tem
        folgas_por_funcionario = {}
        for funcionario in self.funcionarios:
            folgas_por_funcionario[funcionario.id] = len(self.restricoes.get(funcionario.id, set()))
        
        # Para cada dia, verificar se há funcionários suficientes
        for dia in self.dias:
            funcionarios_disponiveis = 0
            for funcionario in self.funcionarios:
                if dia not in self.restricoes.get(funcionario.id, set()):
                    funcionarios_disponiveis += 1
            
            necessarios = funcionarios_por_dia[dia]
            
            # Se não há funcionários suficientes, remover algumas folgas
            if funcionarios_disponiveis < necessarios:
                print(f"  Dia {dia}: {funcionarios_disponiveis}/{necessarios} funcionários")
                
                # Encontrar funcionários com folga neste dia, ordenados por quem tem mais folgas
                funcionarios_com_folga = []
                for funcionario in self.funcionarios:
                    if dia in self.restricoes.get(funcionario.id, set()):
                        funcionarios_com_folga.append((funcionario, folgas_por_funcionario[funcionario.id]))
                
                # Ordenar por quem tem mais folgas (mais justo)
                funcionarios_com_folga.sort(key=lambda x: x[1], reverse=True)
                
                # Remover folgas até ter funcionários suficientes
                folgas_para_remover = necessarios - funcionarios_disponiveis
                funcionarios_para_remover_folga = funcionarios_com_folga[:folgas_para_remover]
                
                for funcionario, _ in funcionarios_para_remover_folga:
                    if funcionario.id in self.restricoes:
                        self.restricoes[funcionario.id].discard(dia)
                        folgas_por_funcionario[funcionario.id] -= 1
                        print(f"    Removida folga de {funcionario.nome} no dia {dia}")
        
        # Recalcular estatísticas
        total_funcionarios_disponiveis = 0
        for funcionario in self.funcionarios:
            folgas_funcionario = len(self.restricoes.get(funcionario.id, set()))
            dias_disponiveis = len(self.dias) - folgas_funcionario
            total_funcionarios_disponiveis += dias_disponiveis
        
        print(f"✅ Após ajuste: {total_funcionarios_disponiveis} funcionários disponíveis")
        
        # Verificar se agora há funcionários suficientes
        total_turnos_necessarios = sum(funcionarios_por_dia.values())
        if total_funcionarios_disponiveis >= total_turnos_necessarios:
            print("✅ Agora há funcionários suficientes para preencher todos os turnos!")
        else:
            print("❌ Ainda não há funcionários suficientes!")
    
    def gerar_escala_mensal_completa(self):
        """Gera a escala para o mês inteiro de uma só vez"""
        print(f"=== GERANDO ESCALA MENSAL COMPLETA ===")
        print(f"Mês/Ano: {self.mes}/{self.ano}")
        print(f"Valência: {self.valencia}")
        
        # Carregar dados
        self.carregar_dados()
        
        # Logs detalhados para diagnóstico
        print(f"DEBUG: Funcionários encontrados: {len(self.funcionarios)}")
        print(f"DEBUG: Turnos encontrados: {len(self.turnos)}")
        print(f"DEBUG: Configuração encontrada: {self.config is not None}")
        print(f"DEBUG: Dias de funcionamento: {len(self.dias)}")
        
        if not self.funcionarios:
            print("❌ Nenhum funcionário encontrado para esta valência!")
            return None
        
        if not self.turnos:
            print("❌ Nenhum turno encontrado para esta valência!")
            return None
        
        # Configuração é opcional - se não existir, usar valores padrão
        if not self.config:
            print("⚠️  Nenhuma configuração encontrada para esta valência. Usando valores padrão.")
            # Criar configuração padrão
            from datetime import time
            self.config = type('ConfigPadrao', (), {
                'dias_funcionamento': '["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]',
                'ativar_rodizio': False
            })()
        
        print(f"Funcionários: {len(self.funcionarios)}")
        print(f"Turnos: {len(self.turnos)}")
        print(f"Dias de funcionamento: {len(self.dias)}")
        
        # Verificar restrições aplicadas
        total_restricoes = sum(len(restricoes) for restricoes in self.restricoes.values())
        print(f"Total de restrições aplicadas: {total_restricoes}")
        
        # Preparar dados para o solver
        funcionarios_dict = [{'id': f.id, 'nome': f.nome} for f in self.funcionarios]
        turnos_dict = [{'id': t.id, 'nome': t.nome} for t in self.turnos]
        
        # Turnos necessários por dia (apenas dias de funcionamento)
        turnos_necessarios_por_dia = {}
        for dia in self.dias:
            turnos_necessarios = []
            for t in self.turnos:
                turnos_necessarios.append(t.funcionarios_necessarios)
            turnos_necessarios_por_dia[dia] = turnos_necessarios
        
        # Sequências proibidas
        sequencias_proibidas = [
            ('N', 'M'), ('M', 'T'), ('I', 'T'), ('I', 'N'), ('T', 'N'),
        ]
        
        print(f"\n=== RESOLVENDO ESCALA MENSAL COMPLETA ===")
        print(f"Dias a processar: {[d.strftime('%d/%m') for d in self.dias]}")
        
        # Chamar o solver para o mês inteiro
        resultado = gerar_escala_ortools(
            funcionarios_dict,
            turnos_dict,
            self.dias,
            self.restricoes,
            turnos_necessarios_por_dia,
            sequencias_proibidas,
            self.perfil_ideal
        )
        
        if resultado:
            print(f"✅ Escala mensal gerada com sucesso!")
            print(f"Total de escalas: {len(resultado)}")
            
            # Mostrar estatísticas finais
            self.mostrar_estatisticas_escala(resultado)
            
            return resultado
        else:
            print("❌ Falha ao gerar escala mensal!")
            return None
    
    def mostrar_estatisticas_escala(self, escalas):
        """Mostra estatísticas da escala para acompanhar a qualidade"""
        if not escalas:
            return
        
        # Contar turnos por funcionário
        turnos_por_funcionario = defaultdict(int)
        for escala in escalas:
            turnos_por_funcionario[escala['funcionario_id']] += 1
        
        # Calcular estatísticas
        turnos_list = list(turnos_por_funcionario.values())
        if turnos_list:
            media = sum(turnos_list) / len(turnos_list)
            min_turnos = min(turnos_list)
            max_turnos = max(turnos_list)
            
            print(f"\nEstatísticas da Escala:")
            print(f"  Média de turnos por funcionário: {media:.1f}")
            print(f"  Mínimo: {min_turnos} turnos")
            print(f"  Máximo: {max_turnos} turnos")
            print(f"  Variação: {max_turnos - min_turnos} turnos")
            
            # Mostrar distribuição detalhada
            print(f"\nDistribuição por funcionário:")
            funcionarios_dict = {f.id: f.nome for f in self.funcionarios}
            for funcionario_id, total in sorted(turnos_por_funcionario.items()):
                nome = funcionarios_dict.get(funcionario_id, f"Funcionário {funcionario_id}")
                print(f"  {nome}: {total} turnos")
            
            # Alertar se há desequilíbrios graves
            if max_turnos > 25:
                print(f"  ⚠️  ALERTA: Funcionário com {max_turnos} turnos (muito alto)")
            if min_turnos < 10:
                print(f"  ⚠️  ALERTA: Funcionário com {min_turnos} turnos (muito baixo)")
    
    def salvar_escala_otimizada(self, escalas):
        """Salva a escala otimizada no banco de dados"""
        if not escalas:
            print("❌ Nenhuma escala para salvar!")
            return False
        
        with get_app_context():
            # Limpar escalas existentes
            data_inicio = datetime(self.ano, self.mes, 1)
            data_fim = datetime(self.ano, self.mes + 1, 1) - timedelta(days=1)
            
            Escala.query.filter(
                Escala.data >= data_inicio.date(),
                Escala.data <= data_fim.date(),
                Escala.valencia == self.valencia
            ).delete()
            
            # Salvar novas escalas
            escalas_salvas = 0
            for escala in escalas:
                try:
                    nova_escala = Escala(
                        funcionario_id=escala['funcionario_id'],
                        turno_id=escala['turno_id'],
                        data=escala['data'],
                        valencia=self.valencia
                    )
                    db.session.add(nova_escala)
                    escalas_salvas += 1
                except Exception as e:
                    print(f"Erro ao salvar escala: {e}")
            
            try:
                db.session.commit()
                print(f"✅ {escalas_salvas} escalas otimizadas salvas!")
                return True
            except Exception as e:
                print(f"❌ Erro ao salvar: {e}")
                db.session.rollback()
                return False

# Função principal para usar o otimizador
def gerar_escala_mensal_otimizada(mes, ano, valencia):
    """Gera uma escala mensal otimizada"""
    otimizador = OtimizadorMensal(mes, ano, valencia)
    melhor_escala = otimizador.gerar_escala_mensal_completa()
    
    if melhor_escala:
        sucesso = otimizador.salvar_escala_otimizada(melhor_escala)
        if sucesso:
            print("🎉 Escala mensal otimizada gerada com sucesso!")
            return True
        else:
            print("❌ Erro ao salvar escala otimizada!")
            return False
    else:
        print("❌ Falha ao gerar escala mensal!")
        return False

if __name__ == "__main__":
    # Exemplo de como usar o otimizador
    gerar_escala_mensal_otimizada(8, 2025, "Lar de Idosos")