from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import json
import logging
import os
from functools import wraps
from dotenv import load_dotenv
from sqlalchemy.orm import joinedload
from config import config
from models import db, Funcionario, Restricao, Turno, Escala, Configuracao
from otimizador_mensal import OtimizadorMensal

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carregar variáveis de ambiente
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'sua_chave_secreta_aqui'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///instance/escalas.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Configurar a aplicação baseada no ambiente
config_name = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config[config_name])

# Inicializar SQLAlchemy com a aplicação
db.init_app(app)

# Funções helper para tratamento de erros consistentes
def flash_success(message):
    """Exibe mensagem de sucesso padronizada"""
    flash(message, 'success')

def flash_error(message):
    """Exibe mensagem de erro padronizada"""
    flash(message, 'error')

def flash_warning(message):
    """Exibe mensagem de aviso padronizada"""
    flash(message, 'warning')

def flash_info(message):
    """Exibe mensagem informativa padronizada"""
    flash(message, 'info')

def handle_database_error(func):
    """Decorator para tratamento consistente de erros de banco de dados"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Erro de banco de dados em {func.__name__}: {str(e)}")
            flash_error("Ocorreu um erro ao processar sua solicitação. Tente novamente.")
            return redirect(url_for('index'))
    return wrapper

def validate_required_fields(data, required_fields):
    """Valida campos obrigatórios e retorna lista de erros"""
    errors = []
    for field in required_fields:
        if not data.get(field, '').strip():
            errors.append(f"O campo '{field}' é obrigatório.")
    return errors

def safe_int_conversion(value, field_name, min_val=None, max_val=None):
    """Converte valor para inteiro de forma segura"""
    try:
        result = int(value)
        if min_val is not None and result < min_val:
            return None, f"O valor de '{field_name}' deve ser pelo menos {min_val}."
        if max_val is not None and result > max_val:
            return None, f"O valor de '{field_name}' deve ser no máximo {max_val}."
        return result, None
    except (ValueError, TypeError):
        return None, f"O valor de '{field_name}' deve ser um número válido."

@app.route('/')
def index():
    # Otimizar queries com joinedload
    funcionarios = Funcionario.query.filter_by(ativo=True).options(joinedload(Funcionario.restricoes)).all()
    turnos = Turno.query.all()
    escalas = Escala.query.options(joinedload(Escala.funcionario), joinedload(Escala.turno)).all()
    valencias = db.session.query(Configuracao.valencia).distinct().all()
    valencias = [v[0] for v in valencias]
    
    return render_template('index.html', 
                         funcionarios=funcionarios,
                         turnos=turnos,
                         escalas=escalas,
                         valencias=valencias)

@app.route('/funcionarios')
def funcionarios():
    mostrar_inativos = request.args.get('mostrar_inativos', 'false').lower() == 'true'
    
    if mostrar_inativos:
        funcionarios = Funcionario.query.options(joinedload(Funcionario.restricoes)).all()
    else:
        funcionarios = Funcionario.query.filter_by(ativo=True).options(joinedload(Funcionario.restricoes)).all()
    
    return render_template('funcionarios.html', funcionarios=funcionarios, mostrar_inativos=mostrar_inativos)

@app.route('/funcionarios/adicionar', methods=['GET', 'POST'])
@handle_database_error
def adicionar_funcionario():
    if request.method == 'POST':
        # Validar campos obrigatórios
        required_fields = ['nome', 'valencia']
        errors = validate_required_fields(request.form, required_fields)
        
        if errors:
            for error in errors:
                flash_error(error)
            return render_template('adicionar_funcionario.html')
        
        try:
            funcionario = Funcionario(
                nome=request.form['nome'].strip(),
                valencia=request.form['valencia'],
                ativo=True
            )
            db.session.add(funcionario)
            db.session.commit()
            flash_success('Funcionário adicionado com sucesso!')
            return redirect(url_for('funcionarios'))
        except Exception as e:
            logger.error(f"Erro ao adicionar funcionário: {str(e)}")
            flash_error("Erro ao adicionar funcionário. Tente novamente.")
            return render_template('adicionar_funcionario.html')
    
    return render_template('adicionar_funcionario.html')

@app.route('/funcionarios/<int:id>/restricoes')
def restricoes_funcionario(id):
    funcionario = Funcionario.query.options(joinedload(Funcionario.restricoes)).get_or_404(id)
    restricoes = funcionario.restricoes
    return render_template('restricoes_conteudo.html', funcionario=funcionario, restricoes=restricoes)

@app.route('/funcionarios/<int:id>/eliminar', methods=['POST'])
@handle_database_error
def eliminar_funcionario(id):
    funcionario = Funcionario.query.get_or_404(id)
    
    # Verificar se há escalas futuras
    escalas_futuras = db.session.query(db.func.count(Escala.id)).filter(
        Escala.funcionario_id == id,
        Escala.data >= datetime.now().date()
    ).scalar()
    
    if escalas_futuras > 0:
        flash_error(f'Não é possível eliminar o funcionário {funcionario.nome} pois tem {escalas_futuras} escalas futuras.')
        return redirect(url_for('funcionarios'))
    
    try:
        db.session.delete(funcionario)
        db.session.commit()
        flash_success(f'Funcionário {funcionario.nome} eliminado com sucesso!')
    except Exception as e:
        logger.error(f"Erro ao eliminar funcionário: {str(e)}")
        flash_error("Erro ao eliminar funcionário. Tente novamente.")
    
    return redirect(url_for('funcionarios'))

@app.route('/funcionarios/<int:id>/desativar', methods=['POST'])
@handle_database_error
def desativar_funcionario(id):
    funcionario = Funcionario.query.get_or_404(id)
    
    try:
        funcionario.ativo = False
        db.session.commit()
        flash_success(f'Funcionário {funcionario.nome} desativado com sucesso!')
    except Exception as e:
        logger.error(f"Erro ao desativar funcionário: {str(e)}")
        flash_error("Erro ao desativar funcionário. Tente novamente.")
    
    return redirect(url_for('funcionarios'))

@app.route('/funcionarios/<int:id>/ativar', methods=['POST'])
@handle_database_error
def ativar_funcionario(id):
    funcionario = Funcionario.query.get_or_404(id)
    
    try:
        funcionario.ativo = True
        db.session.commit()
        flash_success(f'Funcionário {funcionario.nome} ativado com sucesso!')
    except Exception as e:
        logger.error(f"Erro ao ativar funcionário: {str(e)}")
        flash_error("Erro ao ativar funcionário. Tente novamente.")
    
    return redirect(url_for('funcionarios'))

@app.route('/funcionarios/<int:id>/restricoes/adicionar', methods=['POST'])
@handle_database_error
def adicionar_restricao(id):
    funcionario = Funcionario.query.get_or_404(id)
    
    # Validar campos obrigatórios
    required_fields = ['tipo', 'data_inicio', 'data_fim']
    errors = validate_required_fields(request.form, required_fields)
    
    if errors:
        for error in errors:
            flash_error(error)
        return redirect(url_for('restricoes_funcionario', id=id))
    
    try:
        # Validar datas
        data_inicio = datetime.strptime(request.form['data_inicio'], '%Y-%m-%d').date()
        data_fim = datetime.strptime(request.form['data_fim'], '%Y-%m-%d').date()
        
        if data_inicio > data_fim:
            flash_error("A data de início não pode ser posterior à data de fim.")
            return redirect(url_for('restricoes_funcionario', id=id))
        
        restricao = Restricao(
            funcionario_id=id,
            tipo=request.form['tipo'],
            data_inicio=data_inicio,
            data_fim=data_fim
        )
        db.session.add(restricao)
        db.session.commit()
        flash_success('Restrição adicionada com sucesso!')
    except ValueError:
        flash_error("Formato de data inválido. Use o formato AAAA-MM-DD.")
    except Exception as e:
        logger.error(f"Erro ao adicionar restrição: {str(e)}")
        flash_error("Erro ao adicionar restrição. Tente novamente.")
    
    return redirect(url_for('restricoes_funcionario', id=id))

@app.route('/restricoes/<int:id>/eliminar', methods=['POST'])
def eliminar_restricao(id):
    restricao = Restricao.query.get_or_404(id)
    funcionario_id = restricao.funcionario_id
    funcionario_nome = restricao.funcionario.nome
    
    db.session.delete(restricao)
    db.session.commit()
    
    flash_success(f'Restrição eliminada com sucesso do funcionário {funcionario_nome}!')
    return redirect(url_for('restricoes_funcionario', id=funcionario_id))

@app.route('/turnos')
def turnos():
    turnos = Turno.query.all()
    return render_template('turnos.html', turnos=turnos)

@app.route('/turnos/adicionar', methods=['GET', 'POST'])
@handle_database_error
def adicionar_turno():
    if request.method == 'POST':
        # Validar campos obrigatórios
        required_fields = ['nome', 'valencia', 'funcionarios_necessarios']
        errors = validate_required_fields(request.form, required_fields)
        
        if errors:
            for error in errors:
                flash_error(error)
            return render_template('adicionar_turno.html')
        
        # Validar número de funcionários
        funcionarios_necessarios, error = safe_int_conversion(
            request.form['funcionarios_necessarios'], 
            'funcionários necessários', 
            min_val=1, 
            max_val=50
        )
        
        if error:
            flash_error(error)
            return render_template('adicionar_turno.html')
        
        try:
            turno = Turno(
                nome=request.form['nome'].strip(),
                valencia=request.form['valencia'],
                funcionarios_necessarios=funcionarios_necessarios
            )
            db.session.add(turno)
            db.session.commit()
            flash_success('Turno adicionado com sucesso!')
            return redirect(url_for('turnos'))
        except Exception as e:
            logger.error(f"Erro ao adicionar turno: {str(e)}")
            flash_error("Erro ao adicionar turno. Tente novamente.")
            return render_template('adicionar_turno.html')
    
    return render_template('adicionar_turno.html')

@app.route('/turnos/editar/<int:id>', methods=['GET', 'POST'])
@handle_database_error
def editar_turno(id):
    turno = Turno.query.get_or_404(id)
    
    if request.method == 'POST':
        # Validar campos obrigatórios
        required_fields = ['nome', 'funcionarios_necessarios']
        errors = validate_required_fields(request.form, required_fields)
        
        if errors:
            for error in errors:
                flash_error(error)
            return render_template('adicionar_turno.html', editar=True, turno=turno)
        
        # Validar número de funcionários
        funcionarios_necessarios, error = safe_int_conversion(
            request.form['funcionarios_necessarios'], 
            'funcionários necessários', 
            min_val=1, 
            max_val=50
        )
        
        if error:
            flash_error(error)
            return render_template('adicionar_turno.html', editar=True, turno=turno)
        
        try:
            turno.nome = request.form['nome'].strip()
            turno.funcionarios_necessarios = funcionarios_necessarios
            db.session.commit()
            flash_success('Turno atualizado com sucesso!')
            return redirect(url_for('turnos'))
        except Exception as e:
            logger.error(f"Erro ao atualizar turno: {str(e)}")
            flash_error("Erro ao atualizar turno. Tente novamente.")
            return render_template('adicionar_turno.html', editar=True, turno=turno)
    
    return render_template('adicionar_turno.html', editar=True, turno=turno)

@app.route('/turnos/<int:id>/eliminar', methods=['POST'])
@handle_database_error
def eliminar_turno(id):
    turno = Turno.query.get_or_404(id)
    
    # Verificar se há escalas futuras
    escalas_futuras = db.session.query(db.func.count(Escala.id)).filter(
        Escala.turno_id == id,
        Escala.data >= datetime.now().date()
    ).scalar()
    
    if escalas_futuras > 0:
        flash_error(f'Não é possível eliminar o turno {turno.nome} pois tem {escalas_futuras} escalas futuras.')
        return redirect(url_for('turnos'))
    
    try:
        db.session.delete(turno)
        db.session.commit()
        flash_success(f'Turno {turno.nome} eliminado com sucesso!')
    except Exception as e:
        logger.error(f"Erro ao eliminar turno: {str(e)}")
        flash_error("Erro ao eliminar turno. Tente novamente.")
    
    return redirect(url_for('turnos'))

@app.route('/configuracoes')
def configuracoes():
    configs = Configuracao.query.all()
    return render_template('configuracoes.html', configs=configs)

@app.route('/configuracoes/adicionar', methods=['GET', 'POST'])
def adicionar_configuracao():
    if request.method == 'POST':
        erros = []
        valencia = request.form.get('valencia', '').strip()
        hora_abertura_str = request.form.get('hora_abertura', '').strip()
        hora_fecho_str = request.form.get('hora_fecho', '').strip()
        dias_funcionamento_list = request.form.getlist('dias_funcionamento')

        # Validação básica
        if not valencia:
            erros.append('A valência é obrigatória.')
        if not hora_abertura_str:
            erros.append('A hora de abertura é obrigatória.')
        if not hora_fecho_str:
            erros.append('A hora de fecho é obrigatória.')
        if not dias_funcionamento_list:
            erros.append('Selecione pelo menos um dia de funcionamento.')

        # Validação de horários
        try:
            hora_abertura = datetime.strptime(hora_abertura_str, '%H:%M').time()
        except Exception:
            erros.append('Hora de abertura inválida.')
            hora_abertura = None
        try:
            hora_fecho = datetime.strptime(hora_fecho_str, '%H:%M').time()
        except Exception:
            erros.append('Hora de fecho inválida.')
            hora_fecho = None
        if hora_abertura and hora_fecho and hora_abertura >= hora_fecho:
            erros.append('A hora de abertura deve ser anterior à hora de fecho.')

        dias_funcionamento = json.dumps(dias_funcionamento_list)

        # Validação de rodízio
        ativar_rodizio = 'ativar_rodizio' in request.form
        data_inicio_rodizio = None
        padrao_rodizio = None
        if ativar_rodizio:
            data_inicio_rodizio_str = request.form.get('data_inicio_rodizio', '').strip()
            if not data_inicio_rodizio_str:
                erros.append('A data de início do rodízio é obrigatória.')
            else:
                try:
                    data_inicio_rodizio = datetime.strptime(data_inicio_rodizio_str, '%Y-%m-%d').date()
                    if data_inicio_rodizio < datetime.now().date():
                        erros.append('A data de início do rodízio não pode ser no passado.')
                except Exception:
                    erros.append('Data de início do rodízio inválida.')
            # Validação do padrão de rodízio
            padrao_rodizio = []
            i = 0
            while f'periodo_{i}_tipo' in request.form:
                tipo = request.form[f'periodo_{i}_tipo']
                try:
                    dias = int(request.form[f'periodo_{i}_dias'])
                except Exception:
                    erros.append(f'Número de dias inválido no período {i+1}.')
                    dias = 0
                if tipo not in ['trabalho', 'folga']:
                    erros.append(f'Tipo de período inválido no período {i+1}.')
                if dias < 1 or dias > 31:
                    erros.append(f'O número de dias no período {i+1} deve estar entre 1 e 31.')
                padrao_rodizio.append({'tipo': tipo, 'dias': dias})
                i += 1
            if not padrao_rodizio:
                erros.append('Defina pelo menos um período no padrão de rodízio.')
            else:
                padrao_rodizio = json.dumps(padrao_rodizio)

        # Se houver erros, exibir e retornar para o formulário
        if erros:
            for erro in erros:
                flash_error(erro)
            return render_template('adicionar_configuracao.html', editar=False, config=None, dias_funcionamento=dias_funcionamento_list, padrao_rodizio=padrao_rodizio)

        # Se passou por todas as validações, salvar
        config = Configuracao(
            valencia=valencia,
            hora_abertura=hora_abertura,
            hora_fecho=hora_fecho,
            dias_funcionamento=dias_funcionamento,
            ativar_rodizio=ativar_rodizio,
            data_inicio_rodizio=data_inicio_rodizio,
            padrao_rodizio=padrao_rodizio
        )
        db.session.add(config)
        db.session.commit()
        flash_success('Configuração adicionada com sucesso!')
        return redirect(url_for('configuracoes'))
    return render_template('adicionar_configuracao.html', editar=False, config=None, dias_funcionamento=[], padrao_rodizio=None)

@app.route('/configuracoes/editar/<int:id>', methods=['GET', 'POST'])
@handle_database_error
def editar_configuracao(id):
    config = Configuracao.query.get_or_404(id)
    
    if request.method == 'POST':
        erros = []
        valencia = request.form.get('valencia', '').strip()
        hora_abertura_str = request.form.get('hora_abertura', '').strip()
        hora_fecho_str = request.form.get('hora_fecho', '').strip()
        dias_funcionamento_list = request.form.getlist('dias_funcionamento')

        # Validação básica
        if not valencia:
            erros.append('A valência é obrigatória.')
        if not hora_abertura_str:
            erros.append('A hora de abertura é obrigatória.')
        if not hora_fecho_str:
            erros.append('A hora de fecho é obrigatória.')
        if not dias_funcionamento_list:
            erros.append('Selecione pelo menos um dia de funcionamento.')

        # Validação de horários
        try:
            hora_abertura = datetime.strptime(hora_abertura_str, '%H:%M').time()
        except Exception:
            erros.append('Hora de abertura inválida.')
            hora_abertura = None
        try:
            hora_fecho = datetime.strptime(hora_fecho_str, '%H:%M').time()
        except Exception:
            erros.append('Hora de fecho inválida.')
            hora_fecho = None
        if hora_abertura and hora_fecho and hora_abertura >= hora_fecho:
            erros.append('A hora de abertura deve ser anterior à hora de fecho.')

        dias_funcionamento = json.dumps(dias_funcionamento_list)

        # Validação de rodízio
        ativar_rodizio = 'ativar_rodizio' in request.form
        data_inicio_rodizio = None
        padrao_rodizio = None
        if ativar_rodizio:
            data_inicio_rodizio_str = request.form.get('data_inicio_rodizio', '').strip()
            if not data_inicio_rodizio_str:
                erros.append('A data de início do rodízio é obrigatória.')
            else:
                try:
                    data_inicio_rodizio = datetime.strptime(data_inicio_rodizio_str, '%Y-%m-%d').date()
                    if data_inicio_rodizio < datetime.now().date():
                        erros.append('A data de início do rodízio não pode ser no passado.')
                except Exception:
                    erros.append('Data de início do rodízio inválida.')
            # Validação do padrão de rodízio
            padrao_rodizio = []
            i = 0
            while f'periodo_{i}_tipo' in request.form:
                tipo = request.form[f'periodo_{i}_tipo']
                try:
                    dias = int(request.form[f'periodo_{i}_dias'])
                except Exception:
                    erros.append(f'Número de dias inválido no período {i+1}.')
                    dias = 0
                if tipo not in ['trabalho', 'folga']:
                    erros.append(f'Tipo de período inválido no período {i+1}.')
                if dias < 1 or dias > 31:
                    erros.append(f'O número de dias no período {i+1} deve estar entre 1 e 31.')
                padrao_rodizio.append({'tipo': tipo, 'dias': dias})
                i += 1
            if not padrao_rodizio:
                erros.append('Defina pelo menos um período no padrão de rodízio.')
            else:
                padrao_rodizio = json.dumps(padrao_rodizio)

        # Se houver erros, exibir e retornar para o formulário
        if erros:
            for erro in erros:
                flash_error(erro)
            dias_funcionamento = json.loads(config.dias_funcionamento) if config.dias_funcionamento else []
            padrao_rodizio = []
            if config.padrao_rodizio:
                try:
                    padrao_rodizio = json.loads(config.padrao_rodizio)
                except:
                    padrao_rodizio = []
            return render_template('adicionar_configuracao.html', editar=True, config=config, dias_funcionamento=dias_funcionamento, padrao_rodizio=padrao_rodizio)

        # Se passou por todas as validações, salvar
        try:
            config.valencia = valencia
            config.hora_abertura = hora_abertura
            config.hora_fecho = hora_fecho
            config.dias_funcionamento = dias_funcionamento
            config.ativar_rodizio = ativar_rodizio
            config.data_inicio_rodizio = data_inicio_rodizio
            config.padrao_rodizio = padrao_rodizio
            db.session.commit()
            flash_success('Configuração atualizada com sucesso!')
            return redirect(url_for('configuracoes'))
        except Exception as e:
            logger.error(f"Erro ao atualizar configuração: {str(e)}")
            flash_error("Erro ao atualizar configuração. Tente novamente.")
    
    # Preparar dados para o template
    dias_funcionamento = json.loads(config.dias_funcionamento) if config.dias_funcionamento else []
    padrao_rodizio = []
    if config.padrao_rodizio:
        try:
            padrao_rodizio = json.loads(config.padrao_rodizio)
        except:
            padrao_rodizio = []
    return render_template('adicionar_configuracao.html', editar=True, config=config, dias_funcionamento=dias_funcionamento, padrao_rodizio=padrao_rodizio)

@app.route('/configuracoes/eliminar/<int:id>', methods=['POST'])
def eliminar_configuracao(id):
    config = Configuracao.query.get_or_404(id)
    valencia = config.valencia
    
    # Verificar se há escalas futuras para esta valência usando query otimizada
    escalas_futuras = db.session.query(db.func.count(Escala.id)).filter(
        Escala.valencia == valencia,
        Escala.data >= datetime.now().date()
    ).scalar()
    
    if escalas_futuras > 0:
        flash_error(f'Não é possível eliminar a configuração de {valencia} pois existem {escalas_futuras} escalas futuras.')
        return redirect(url_for('configuracoes'))
    
    # Eliminar a configuração
    db.session.delete(config)
    db.session.commit()
    
    flash_success(f'Configuração de {valencia} eliminada com sucesso!')
    return redirect(url_for('configuracoes'))

@app.route('/configuracoes/apagar_escalas_futuras/<int:id>', methods=['POST'])
def apagar_escalas_futuras(id):
    config = Configuracao.query.get_or_404(id)
    valencia = config.valencia
    
    # Apagar todas as escalas futuras para esta valência
    num_apagadas = Escala.query.filter(
        Escala.valencia == valencia,
        Escala.data >= datetime.now().date()
    ).delete(synchronize_session=False)
    db.session.commit()
    flash_success(f'{num_apagadas} escalas futuras apagadas para {valencia}.')
    return redirect(url_for('configuracoes'))

@app.route('/escalas')
def escalas():
    mes = request.args.get('mes', datetime.now().month)
    ano = request.args.get('ano', datetime.now().year)
    valencia = request.args.get('valencia', '')
    
    # Buscar escalas do mês com queries otimizadas
    data_inicio = datetime(int(ano), int(mes), 1).date()
    if int(mes) == 12:
        data_fim = datetime(int(ano) + 1, 1, 1).date() - timedelta(days=1)
    else:
        data_fim = datetime(int(ano), int(mes) + 1, 1).date() - timedelta(days=1)
    
    # Filtrar por valência se especificada
    query = Escala.query.filter(
        Escala.data >= data_inicio,
        Escala.data <= data_fim
    ).options(joinedload(Escala.funcionario), joinedload(Escala.turno))
    
    if valencia:
        query = query.filter(Escala.valencia == valencia)
    
    escalas = query.all()
    
    # Calcular total de dias trabalhados por funcionário usando agregação na base de dados
    total_trabalhados_por_funcionario = {}
    if escalas:
        # Usar query de agregação para melhor performance
        resultados = db.session.query(
            Escala.funcionario_id,
            db.func.count(Escala.id).label('total')
        ).filter(
            Escala.data >= data_inicio,
            Escala.data <= data_fim
        )
        
        if valencia:
            resultados = resultados.filter(Escala.valencia == valencia)
        
        resultados = resultados.group_by(Escala.funcionario_id).all()
        
        for funcionario_id, total in resultados:
            total_trabalhados_por_funcionario[funcionario_id] = total
    
    return render_template('escalas.html', escalas=escalas, mes=mes, ano=ano, valencia=valencia, total_trabalhados_por_funcionario=total_trabalhados_por_funcionario, datetime=datetime)

@app.route('/escalas/gerar', methods=['POST'])
def gerar_escalas():
    """Centraliza toda a lógica de geração de escalas no OtimizadorMensal"""
    mes = int(request.form['mes'])
    ano = int(request.form['ano'])
    valencia = request.form['valencia']
    tipo_geracao = request.form.get('tipo_geracao', 'otimizada')  # Por padrão, usar otimizada

    try:
        # Importar o otimizador de forma lazy para evitar importação circular
        otimizador = OtimizadorMensal(mes, ano, valencia)
        melhor_escala = otimizador.gerar_escala_mensal_completa()
        
        if melhor_escala:
            flash_success(f'Escala mensal gerada com sucesso para {valencia}!')
        else:
            flash_error('Erro ao gerar escala. Verifique se há funcionários e turnos suficientes.')
        
    except Exception as e:
        flash_error(f'Erro inesperado ao gerar escala: {str(e)}')
    
    return redirect(url_for('escalas'))

# Filtro customizado para Jinja2
@app.template_filter('from_json')
def from_json_filter(s):
    try:
        return json.loads(s)
    except Exception:
        return []

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True) 