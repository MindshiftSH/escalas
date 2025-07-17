# Sistema de Tratamento de Erros - Sistema de Escalas

## Visão Geral

Este documento descreve o sistema de tratamento de erros implementado para garantir consistência e melhor experiência do usuário.

## Componentes Implementados

### 1. Funções Helper (app.py)

#### Funções de Flash
- `flash_success(message)`: Mensagens de sucesso
- `flash_error(message)`: Mensagens de erro
- `flash_warning(message)`: Mensagens de aviso
- `flash_info(message)`: Mensagens informativas

#### Funções de Validação
- `validate_required_fields(data, required_fields)`: Valida campos obrigatórios
- `safe_int_conversion(value, field_name, min_val, max_val)`: Conversão segura de inteiros

#### Decorator de Tratamento de Erros
- `@handle_database_error`: Trata erros de banco de dados automaticamente

### 2. Tipos de Mensagens

| Tipo | Cor | Ícone | Uso |
|------|-----|-------|-----|
| success | Verde | ✓ | Operações bem-sucedidas |
| error | Vermelho | ⚠ | Erros críticos |
| warning | Amarelo | ⚠ | Avisos importantes |
| info | Azul | ℹ | Informações gerais |

### 3. Validação Frontend (HTML/JS)

#### Atributos HTML5
- `required`: Campos obrigatórios
- `min/max`: Limites numéricos
- `type`: Validação de tipo (email, number, date, etc.)

#### Validação JavaScript
- Verificação automática de formulários
- Feedback visual imediato
- Prevenção de submissão inválida

### 4. Validação Backend (Python/Flask)

#### Validação de Campos
```python
# Exemplo de validação
required_fields = ['nome', 'valencia']
errors = validate_required_fields(request.form, required_fields)
if errors:
    for error in errors:
        flash_error(error)
```

#### Tratamento de Exceções
```python
try:
    # Operação crítica
    db.session.commit()
    flash_success('Operação realizada com sucesso!')
except Exception as e:
    logger.error(f"Erro: {str(e)}")
    flash_error("Erro ao processar solicitação.")
```

## Padrões de Uso

### 1. Validação de Formulários
```python
@app.route('/exemplo', methods=['POST'])
def exemplo():
    # Validar campos obrigatórios
    required_fields = ['campo1', 'campo2']
    errors = validate_required_fields(request.form, required_fields)
    
    if errors:
        for error in errors:
            flash_error(error)
        return render_template('formulario.html')
    
    # Processar dados válidos
    flash_success('Dados salvos com sucesso!')
    return redirect(url_for('lista'))
```

### 2. Tratamento de Operações Críticas
```python
@app.route('/operacao-critica', methods=['POST'])
@handle_database_error
def operacao_critica():
    try:
        # Operação que pode falhar
        resultado = operacao_complexa()
        flash_success('Operação realizada com sucesso!')
        return redirect(url_for('sucesso'))
    except Exception as e:
        logger.error(f"Erro na operação: {str(e)}")
        flash_error("Erro ao processar operação.")
        return redirect(url_for('erro'))
```

### 3. Validação de Dados Numéricos
```python
valor, error = safe_int_conversion(
    request.form['quantidade'], 
    'quantidade', 
    min_val=1, 
    max_val=100
)

if error:
    flash_error(error)
    return render_template('formulario.html')
```

## Benefícios

### 1. Consistência
- Todas as mensagens seguem o mesmo padrão
- Cores e ícones padronizados
- Comportamento uniforme em toda a aplicação

### 2. Experiência do Usuário
- Feedback claro e imediato
- Mensagens em português
- Auto-hide de mensagens após 5 segundos

### 3. Manutenibilidade
- Código centralizado e reutilizável
- Logs estruturados para debugging
- Fácil de estender e modificar

### 4. Segurança
- Validação tanto no frontend quanto backend
- Prevenção de dados inválidos
- Tratamento seguro de exceções

## Exemplos de Uso

### Validação de Funcionário
```python
# Validar campos obrigatórios
required_fields = ['nome', 'valencia']
errors = validate_required_fields(request.form, required_fields)

# Validar dados específicos
if not errors:
    nome = request.form['nome'].strip()
    if len(nome) < 2:
        errors.append('Nome deve ter pelo menos 2 caracteres.')

# Exibir erros ou salvar
if errors:
    for error in errors:
        flash_error(error)
else:
    # Salvar funcionário
    flash_success('Funcionário adicionado com sucesso!')
```

### Validação de Configuração
```python
# Validar horários
try:
    hora_abertura = datetime.strptime(request.form['hora_abertura'], '%H:%M').time()
    hora_fecho = datetime.strptime(request.form['hora_fecho'], '%H:%M').time()
    
    if hora_abertura >= hora_fecho:
        flash_error('Hora de abertura deve ser anterior à hora de fecho.')
except ValueError:
    flash_error('Formato de horário inválido.')
```

## Logs e Debugging

### Estrutura de Logs
```python
import logging

logger = logging.getLogger(__name__)

# Log de erro
logger.error(f"Erro ao salvar funcionário: {str(e)}")

# Log de informação
logger.info(f"Funcionário {nome} adicionado com sucesso")
```

### Monitoramento
- Todos os erros são logados
- Informações estruturadas para análise
- Fácil identificação de problemas

## Conclusão

O sistema de tratamento de erros implementado garante:
- **Consistência** em todas as mensagens
- **Experiência do usuário** melhorada
- **Manutenibilidade** do código
- **Segurança** na validação de dados

Este sistema pode ser facilmente estendido para novos tipos de validação e mensagens conforme necessário. 