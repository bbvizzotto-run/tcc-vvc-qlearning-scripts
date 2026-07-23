import numpy as np

class QLearningAgent:
    def __init__(self, state_space_size, action_space_size, learning_rate=0.1, discount_factor=0.9, epsilon=0.1):
        """
        Inicializa o agente Q-Learning.

        Parâmetros:
        - state_space_size: Tamanho do espaço de estados discretizado.
        - action_space_size: Número de ações disponíveis para o agente.
        - learning_rate (alpha): Taxa de aprendizado para atualização da Q-table.
        - discount_factor (gamma): Fator de desconto para recompensas futuras.
        - epsilon: Probabilidade de exploração (escolha de ação aleatória).
        """
        self.state_space_size = state_space_size
        self.action_space_size = action_space_size
        self.learning_rate = learning_rate  # alpha
        self.discount_factor = discount_factor  # gamma
        self.epsilon = epsilon
        self.q_table = np.zeros((state_space_size, action_space_size))

    def discretize_state(self, buffer_occupancy, current_bitrate, buffer_levels, bitrate_levels):
        """
        Discretiza o estado contínuo do ambiente em um índice de estado para a Q-table.
        A discretização deve ser adaptada com base nos ranges reais e granularidade desejada.

        Parâmetros:
        - buffer_occupancy: Ocupação atual do buffer (valor contínuo).
        - current_bitrate: Bitrate atual da transmissão (valor contínuo).
        - buffer_levels: Limiares para discretização da ocupação do buffer.
        - bitrate_levels: Limiares para discretização do bitrate.

        Retorna:
        - state_index: Índice inteiro que representa o estado discretizado.
        """
        buffer_state = np.digitize(buffer_occupancy, buffer_levels) - 1
        bitrate_state = np.digitize(current_bitrate, bitrate_levels) - 1
        
        buffer_state = max(0, min(buffer_state, len(buffer_levels) - 1))
        bitrate_state = max(0, min(bitrate_state, len(bitrate_levels) - 1))
        
        num_bitrate_states = len(bitrate_levels)
        state_index = buffer_state * num_bitrate_states + bitrate_state
        return state_index

    def choose_action(self, state_index):
        """
        Escolhe uma ação com base na política epsilon-greedy.

        Parâmetros:
        - state_index: Índice do estado atual.

        Retorna:
        - action: Ação escolhida (índice).
        """
        if np.random.uniform(0, 1) < self.epsilon:
            action = np.random.randint(self.action_space_size)  # Exploração
        else:
            action = np.argmax(self.q_table[state_index, :])  # Explotação
        return action

    def update_q_table(self, current_state_index, action, reward, next_state_index):
        """
        Atualiza a Q-table usando a equação de Bellman.

        Parâmetros:
        - current_state_index: Índice do estado anterior.
        - action: Ação tomada.
        - reward: Recompensa recebida.
        - next_state_index: Índice do próximo estado.
        """
        best_next_action_value = np.max(self.q_table[next_state_index, :])
        td_target = reward + self.discount_factor * best_next_action_value
        td_error = td_target - self.q_table[current_state_index, action]
        self.q_table[current_state_index, action] += self.learning_rate * td_error

    def get_action_meaning(self, action):
        """
        Retorna o significado da ação escolhida.

        Parâmetros:
        - action: Índice da ação.

        Retorna:
        - String descrevendo a ação (e.g., "decrease_bitrate").
        """
        if action == 0:
            return "decrease_bitrate"
        elif action == 1:
            return "maintain_bitrate"
        elif action == 2:
            return "increase_bitrate"
        else:
            return "unknown_action"

# Bloco de integração: Como usar o QLearningAgent em um ambiente de streaming real.
if __name__ == "__main__":
    # 1. Definição do Espaço de Estados e Ações:
    #    Baseado na descrição do TCC, o espaço de estados é uma combinação da ocupação do buffer
    #    e do bitrate atual. O espaço de ações inclui diminuir, manter ou aumentar o bitrate.
    
    #    Exemplo de níveis de discretização (ajuste conforme o ambiente real):
    num_buffer_levels = 10  # Número de níveis para a ocupação do buffer
    num_bitrate_levels = 5  # Número de níveis para o bitrate
    state_space_size = num_buffer_levels * num_bitrate_levels
    action_space_size = 3  # 0: diminuir, 1: manter, 2: aumentar bitrate

    #    Defina os limiares para discretização de buffer e bitrate.
    #    Estes valores devem ser determinados experimentalmente ou com base nas especificações do sistema.
    buffer_levels = np.linspace(0, 100, num_buffer_levels + 1)[1:] # Exemplo: 0-100% do buffer máximo
    bitrate_levels = np.array([500, 1000, 2000, 4000, 8000]) # Exemplo: bitrates em kbps

    # 2. Inicialização do Agente:
    agent = QLearningAgent(state_space_size, action_space_size,
                           learning_rate=0.1, discount_factor=0.9, epsilon=0.1)

    # 3. Loop de Treinamento/Operação em Tempo Real:
    #    Este loop deve ser integrado ao sistema de streaming adaptativo.
    #    A cada intervalo de tempo (e.g., a cada segmento de vídeo processado):
    
    #    a. Observar o estado atual do ambiente:
    #       - current_buffer_occupancy: Obtenha a ocupação atual do buffer do reprodutor de vídeo.
    #       - current_bitrate: Obtenha o bitrate atual da transmissão.
    #       - reward: Calcule a recompensa com base na QoE observada (e.g., penalidade por rebuffering, recompensa por alta qualidade).
    
    #    b. Discretizar o estado observado:
    #       current_state_index = agent.discretize_state(current_buffer_occupancy, current_bitrate, buffer_levels, bitrate_levels)
    
    #    c. Escolher uma ação:
    #       action = agent.choose_action(current_state_index)
    #       chosen_bitrate_action = agent.get_action_meaning(action)
    
    #    d. Aplicar a ação no ambiente de streaming:
    #       - Modifique o bitrate da próxima requisição de segmento de vídeo com base em `chosen_bitrate_action`.
    #       - Exemplo: Se `chosen_bitrate_action` for "increase_bitrate", selecione o próximo bitrate disponível mais alto.
    
    #    e. Observar o próximo estado e recompensa (após a aplicação da ação e avanço do tempo):
    #       - next_buffer_occupancy, next_bitrate, next_reward = <obter do ambiente>
    #       - next_state_index = agent.discretize_state(next_buffer_occupancy, next_bitrate, buffer_levels, bitrate_levels)
    
    #    f. Atualizar a Q-table do agente:
    #       agent.update_q_table(current_state_index, action, reward, next_state_index)
    
    # 4. Persistência da Q-table:
    #    Para que o agente "lembre" o que aprendeu, a Q-table deve ser salva e carregada.
    #    Exemplo: np.save("q_table.npy", agent.q_table)
    #    Exemplo: agent.q_table = np.load("q_table.npy")

    print("QLearningAgent configurado. Integre este script ao seu ambiente de streaming adaptativo.")
    print("Consulte os comentários no código para detalhes sobre os pontos de integração.")
