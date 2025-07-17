from ortools.sat.python import cp_model
from datetime import timedelta

def gerar_escala_ortools(funcionarios, turnos, dias, restricoes, turnos_necessarios_por_dia, sequencias_proibidas, perfil_ideal=None):
    """
    funcionarios: lista de dicts com 'id' e 'nome'
    turnos: lista de dicts com 'id' e 'nome' (ex: 'M', 'I', 'T', 'N')
    dias: lista de datas (datetime.date)
    restricoes: dict {funcionario_id: set(dias_folga)}
    turnos_necessarios_por_dia: dict {dia: [n_M, n_I, n_T, n_N]}
    sequencias_proibidas: lista de tuplas [('N','M'), ...]
    perfil_ideal: dict opcional {funcionario_id: {turno: quantidade_ideal}}
    """
    model = cp_model.CpModel()
    n_func = len(funcionarios)
    n_turnos = len(turnos)
    n_dias = len(dias)
    func_idx = {f['id']: i for i, f in enumerate(funcionarios)}
    turno_idx = {t['nome'][0].upper(): i for i, t in enumerate(turnos)}

    # Variáveis: x[f][d][t] = 1 se funcionario f faz turno t no dia d
    x = {}
    for f in range(n_func):
        for d in range(n_dias):
            for t in range(n_turnos):
                x[f, d, t] = model.NewBoolVar(f'x_{f}_{d}_{t}')

    # 1) Cada funcionário faz no máximo 1 turno por dia
    for f in range(n_func):
        for d in range(n_dias):
            model.Add(sum(x[f, d, t] for t in range(n_turnos)) <= 1)

    # 2) OBRIGATÓRIO: Cada turno deve ser preenchido pelo número necessário de funcionários
    # Esta é uma restrição HARD - não pode ser violada
    for d, dia in enumerate(dias):
        for t in range(n_turnos):
            model.Add(sum(x[f, d, t] for f in range(n_func)) == turnos_necessarios_por_dia[dia][t])

    # 3) Proibir sequências de turnos proibidas
    for f in range(n_func):
        for d in range(1, n_dias):
            for ant, atual in sequencias_proibidas:
                if ant in turno_idx and atual in turno_idx:
                    model.AddBoolOr([
                        x[f, d-1, turno_idx[ant]].Not(),
                        x[f, d, turno_idx[atual]].Not()
                    ])

    # 4) Respeitar folgas/restrições (se houver)
    for f in range(n_func):
        id_func = funcionarios[f]['id']
        folgas = restricoes.get(id_func, set())
        for d, dia in enumerate(dias):
            if dia in folgas:
                for t in range(n_turnos):
                    model.Add(x[f, d, t] == 0)

    # 5) EQUILÍBRIO OBRIGATÓRIO - Garantir que todos os funcionários tenham carga adequada
    total_turnos = sum(sum(turnos_necessarios_por_dia[dia]) for dia in dias)
    min_turnos = total_turnos // n_func
    max_turnos = min_turnos + 1
    
    # Forçar que todos os funcionários tenham pelo menos min_turnos e no máximo max_turnos
    for f in range(n_func):
        total_func = sum(x[f, d, t] for d in range(n_dias) for t in range(n_turnos))
        model.Add(total_func >= min_turnos)
        model.Add(total_func <= max_turnos)

    # 6) Garantir que nenhum funcionário trabalhe demais dias consecutivos
    for f in range(n_func):
        for d in range(n_dias - 6):  # Verificar blocos de 7 dias
            # Penalizar se trabalha 7 dias consecutivos
            dias_consecutivos = sum(x[f, d+i, t] for i in range(7) for t in range(n_turnos))
            model.Add(dias_consecutivos <= 6)  # Máximo 6 dias consecutivos

    # 7) Minimizar diferença para o perfil ideal (se existir)
    if perfil_ideal:
        desvios = []
        for f in range(n_func):
            id_func = funcionarios[f]['id']
            for t, turno in enumerate(turnos):
                turno_letra = turno['nome'][0].upper()
                ideal = perfil_ideal.get(id_func, {}).get(turno_letra, 0)
                real = sum(x[f, d, t] for d in range(n_dias))
                desvio = model.NewIntVar(0, 1000, f'desvio_{f}_{t}')
                model.Add(desvio >= real - ideal)
                model.Add(desvio >= ideal - real)
                desvios.append(desvio)
        
        # Minimizar desvios do perfil ideal
        if desvios:
            model.Minimize(sum(desvios))

    # Resolver
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60.0  # Aumentar tempo de resolução
    status = solver.Solve(model)

    resultado = []
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print(f"Solver status: {status}")
        if perfil_ideal:
            print(f"Objetivo: {solver.ObjectiveValue()}")
        
        # Verificar se todos os turnos foram preenchidos
        turnos_nao_preenchidos = 0
        for d, dia in enumerate(dias):
            for t in range(n_turnos):
                funcionarios_no_turno = sum(solver.Value(x[f, d, t]) for f in range(n_func))
                necessarios = turnos_necessarios_por_dia[dia][t]
                if funcionarios_no_turno < necessarios:
                    turnos_nao_preenchidos += necessarios - funcionarios_no_turno
                    print(f"AVISO: Dia {dia}, Turno {turnos[t]['nome']}: {funcionarios_no_turno}/{necessarios}")
        
        if turnos_nao_preenchidos > 0:
            print(f"❌ {turnos_nao_preenchidos} turnos não foram preenchidos!")
            return None
        
        # Construir resultado
        for d, dia in enumerate(dias):
            for t, turno in enumerate(turnos):
                for f, funcionario in enumerate(funcionarios):
                    if solver.Value(x[f, d, t]):
                        resultado.append({
                            'funcionario_id': funcionario['id'],
                            'turno_id': turno['id'],
                            'data': dia
                        })
        
        print(f"✅ Solução encontrada com {len(resultado)} escalas")
        
        # Mostrar estatísticas de equilíbrio
        turnos_por_funcionario = {}
        for f in range(n_func):
            total_func = sum(solver.Value(x[f, d, t]) for d in range(n_dias) for t in range(n_turnos))
            turnos_por_funcionario[funcionarios[f]['nome']] = total_func
        
        print("Distribuição de turnos por funcionário:")
        for nome, total in sorted(turnos_por_funcionario.items()):
            print(f"  {nome}: {total} turnos")
        
        return resultado
    else:
        print(f"❌ Solver falhou: {status}")
        return None 