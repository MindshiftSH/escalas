#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from otimizador_mensal import OtimizadorMensal
from datetime import datetime

def testar_geracao_escala():
    """Testa a geração de escala para verificar se as folgas estão em pares"""
    
    # Testar para um mês específico
    mes = 1  # Janeiro
    ano = 2024
    valencia = "Lar de Idosos"  # Ajustar para uma valência existente
    
    print(f"=== TESTE DE GERAÇÃO DE ESCALA ===")
    print(f"Mês/Ano: {mes}/{ano}")
    print(f"Valência: {valencia}")
    
    try:
        # Criar otimizador
        otimizador = OtimizadorMensal(mes, ano, valencia)
        
        # Carregar dados
        otimizador.carregar_dados()
        
        print(f"\nFuncionários encontrados: {len(otimizador.funcionarios)}")
        print(f"Turnos encontrados: {len(otimizador.turnos)}")
        print(f"Configuração encontrada: {otimizador.config is not None}")
        
        if otimizador.config and otimizador.config.ativar_rodizio:
            print(f"Rodízio ativado: Sim")
            print(f"Data início rodízio: {otimizador.config.data_inicio_rodizio}")
            print(f"Padrão rodízio: {otimizador.config.padrao_rodizio}")
        else:
            print(f"Rodízio ativado: Não")
        
        # Aplicar rodízio automático
        otimizador.aplicar_rodizio_automatico()
        
        # Verificar folgas após aplicação do rodízio
        print(f"\n=== VERIFICAÇÃO DE FOLGAS APÓS RODÍZIO ===")
        for funcionario in otimizador.funcionarios:
            folgas_funcionario = sorted(otimizador.restricoes.get(funcionario.id, set()))
            if folgas_funcionario:
                print(f"\n{funcionario.nome}: {len(folgas_funcionario)} folgas")
                
                # Verificar pares
                pares = []
                folgas_isoladas = []
                i = 0
                while i < len(folgas_funcionario):
                    if i + 1 < len(folgas_funcionario):
                        if (folgas_funcionario[i+1] - folgas_funcionario[i]).days == 1:
                            pares.append((folgas_funcionario[i], folgas_funcionario[i+1]))
                            i += 2
                        else:
                            folgas_isoladas.append(folgas_funcionario[i])
                            i += 1
                    else:
                        folgas_isoladas.append(folgas_funcionario[i])
                        i += 1
                
                print(f"  Pares de folgas: {len(pares)}")
                for par in pares:
                    print(f"    {par[0].strftime('%d/%m')} - {par[1].strftime('%d/%m')}")
                
                if folgas_isoladas:
                    print(f"  ⚠️  Folgas isoladas: {len(folgas_isoladas)}")
                    for folga in folgas_isoladas:
                        print(f"    {folga.strftime('%d/%m')}")
                else:
                    print(f"  ✅ Todas as folgas estão em pares!")
        
        # Tentar gerar a escala
        print(f"\n=== GERANDO ESCALA ===")
        resultado = otimizador.gerar_escala_mensal_completa()
        
        if resultado:
            print(f"✅ Escala gerada com sucesso!")
            print(f"Total de escalas: {len(resultado)}")
            
            # Verificar folgas na escala final
            print(f"\n=== VERIFICAÇÃO FINAL DE FOLGAS ===")
            for funcionario in otimizador.funcionarios:
                # Encontrar dias sem escala para este funcionário
                dias_com_escala = set()
                for escala in resultado:
                    if escala['funcionario_id'] == funcionario.id:
                        dias_com_escala.add(escala['data'])
                
                # Dias de funcionamento sem escala = folgas
                folgas_finais = set(otimizador.dias) - dias_com_escala
                folgas_finais = sorted(folgas_finais)
                
                if folgas_finais:
                    print(f"\n{funcionario.nome}: {len(folgas_finais)} folgas finais")
                    
                    # Verificar pares
                    pares = []
                    folgas_isoladas = []
                    i = 0
                    while i < len(folgas_finais):
                        if i + 1 < len(folgas_finais):
                            if (folgas_finais[i+1] - folgas_finais[i]).days == 1:
                                pares.append((folgas_finais[i], folgas_finais[i+1]))
                                i += 2
                            else:
                                folgas_isoladas.append(folgas_finais[i])
                                i += 1
                        else:
                            folgas_isoladas.append(folgas_finais[i])
                            i += 1
                    
                    print(f"  Pares de folgas: {len(pares)}")
                    for par in pares:
                        print(f"    {par[0].strftime('%d/%m')} - {par[1].strftime('%d/%m')}")
                    
                    if folgas_isoladas:
                        print(f"  ⚠️  Folgas isoladas: {len(folgas_isoladas)}")
                        for folga in folgas_isoladas:
                            print(f"    {folga.strftime('%d/%m')}")
                    else:
                        print(f"  ✅ Todas as folgas estão em pares!")
        else:
            print("❌ Falha ao gerar escala!")
            
    except Exception as e:
        print(f"❌ Erro durante o teste: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    testar_geracao_escala() 