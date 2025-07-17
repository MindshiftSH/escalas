from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Modelos de dados
class Funcionario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    telefone = db.Column(db.String(20))
    valencia = db.Column(db.String(50), nullable=False)
    ativo = db.Column(db.Boolean, default=True)
    restricoes = db.relationship('Restricao', backref='funcionario', lazy=True, cascade='all, delete-orphan')
    escalas = db.relationship('Escala', backref='funcionario', lazy=True, cascade='all, delete-orphan')

class Restricao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)  # 'ferias', 'folga', 'doenca'
    data_inicio = db.Column(db.Date, nullable=False)
    data_fim = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.Text)

class Turno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)
    valencia = db.Column(db.String(50), nullable=False)
    funcionarios_necessarios = db.Column(db.Integer, default=1)
    escalas = db.relationship('Escala', backref='turno', lazy=True, cascade='all, delete-orphan')

class Escala(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False)
    turno_id = db.Column(db.Integer, db.ForeignKey('turno.id'), nullable=False)
    data = db.Column(db.Date, nullable=False)
    valencia = db.Column(db.String(50), nullable=False)

class Configuracao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    valencia = db.Column(db.String(50), nullable=False)
    hora_abertura = db.Column(db.Time, nullable=False)
    hora_fecho = db.Column(db.Time, nullable=False)
    dias_funcionamento = db.Column(db.String(100), nullable=False)  # JSON string
    
    # Campos para rodízio automático
    ativar_rodizio = db.Column(db.Boolean, default=False)
    data_inicio_rodizio = db.Column(db.Date)          # Data de início do padrão
    padrao_rodizio = db.Column(db.String(200))        # JSON string com o padrão personalizado 