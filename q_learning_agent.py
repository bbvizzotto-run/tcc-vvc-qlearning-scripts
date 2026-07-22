
import numpy as np

class QLearningAgent:
    def __init__(self, state_space_size, action_space_size, learning_rate=0.1, discount_factor=0.9, epsilon=0.1):
        self.state_space_size = state_space_size
        self.action_space_size = action_space_size
        self.learning_rate = learning_rate  # alpha
        self.discount_factor = discount_factor  # gamma
        self.epsilon = epsilon
        self.q_table = np.zeros((state_space_size, action_space_size))

    def discretize_state(self, buffer_occupancy, current_bitrate, buffer_levels, bitrate_levels):
        # Example discretization - needs to be adapted based on actual ranges and desired granularity
        buffer_state = np.digitize(buffer_occupancy, buffer_levels) - 1
        bitrate_state = np.digitize(current_bitrate, bitrate_levels) - 1
        
        # Ensure states are within bounds
        buffer_state = max(0, min(buffer_state, len(buffer_levels) - 1))
        bitrate_state = max(0, min(bitrate_state, len(bitrate_levels) - 1))
        
        # Combine into a single state index (assuming state_space_size = len(buffer_levels) * len(bitrate_levels))
        # This mapping needs to be consistent with how state_space_size is defined
        # For simplicity, let's assume a 1D state for now, or a more complex mapping if needed.
        # For a 2D state (buffer_state, bitrate_state), the Q-table would be 2D.
        # Let's assume state_space_size is a tuple (num_buffer_states, num_bitrate_states)
        # and q_table is initialized as np.zeros(state_space_size)
        
        # For now, let's simplify and assume state_space_size is a single integer representing total states
        # and we map (buffer_state, bitrate_state) to a single index.
        # This requires knowing the number of bitrate levels to calculate the unique state index.
        num_bitrate_states = len(bitrate_levels)
        state_index = buffer_state * num_bitrate_states + bitrate_state
        return state_index

    def choose_action(self, state_index):
        if np.random.uniform(0, 1) < self.epsilon:
            action = np.random.randint(self.action_space_size)  # Explore
        else:
            action = np.argmax(self.q_table[state_index, :])  # Exploit
        return action

    def update_q_table(self, current_state_index, action, reward, next_state_index):
        best_next_action_value = np.max(self.q_table[next_state_index, :])
        td_target = reward + self.discount_factor * best_next_action_value
        td_error = td_target - self.q_table[current_state_index, action]
        self.q_table[current_state_index, action] += self.learning_rate * td_error

    def get_action_meaning(self, action):
        # Define what each action means (e.g., 0: decrease bitrate, 1: maintain, 2: increase bitrate)
        if action == 0:
            return "decrease_bitrate"
        elif action == 1:
            return "maintain_bitrate"
        elif action == 2:
            return "increase_bitrate"
        else:
            return "unknown_action"

# Example Usage (conceptual - requires integration with actual streaming environment)
if __name__ == "__main__":
    # Define state and action space parameters based on TCC description
    num_buffer_levels = 10  # N levels for buffer occupancy
    num_bitrate_levels = 5  # M levels for current bitrate
    state_space_size = num_buffer_levels * num_bitrate_levels
    action_space_size = 3  # e.g., decrease, maintain, increase bitrate

    agent = QLearningAgent(state_space_size, action_space_size)

    # Define discretization levels (these would be determined experimentally or based on system specs)
    buffer_levels = np.linspace(0, 100, num_buffer_levels + 1)[1:] # Example: 0-100% buffer
    bitrate_levels = np.array([500, 1000, 2000, 4000, 8000]) # Example bitrates in kbps

    # Simulation loop (conceptual)
    for episode in range(1000):
        current_buffer_occupancy = np.random.uniform(0, 100) # Simulate initial buffer
        current_bitrate = np.random.choice(bitrate_levels) # Simulate initial bitrate
        
        current_state_index = agent.discretize_state(current_buffer_occupancy, current_bitrate, buffer_levels, bitrate_levels)
        
        done = False
        while not done:
            action = agent.choose_action(current_state_index)
            
            # In a real scenario, this would interact with the streaming environment
            # to apply the action and observe the next state and reward.
            # For this example, we'll simulate it.
            
            # Simulate applying action and getting next state/reward
            # (This is highly simplified and needs actual logic from the streaming system)
            if agent.get_action_meaning(action) == "increase_bitrate":
                new_bitrate = min(bitrate_levels[-1], current_bitrate * 1.2)
            elif agent.get_action_meaning(action) == "decrease_bitrate":
                new_bitrate = max(bitrate_levels[0], current_bitrate * 0.8)
            else:
                new_bitrate = current_bitrate
                
            next_buffer_occupancy = np.random.uniform(0, 100) # Simulate next buffer
            reward = np.random.uniform(-1, 1) # Simulate reward
            
            next_state_index = agent.discretize_state(next_buffer_occupancy, new_bitrate, buffer_levels, bitrate_levels)
            
            agent.update_q_table(current_state_index, action, reward, next_state_index)
            
            current_state_index = next_state_index
            current_bitrate = new_bitrate
            
            # Simulate episode termination condition
            if np.random.uniform(0, 1) < 0.01: # 1% chance to end episode
                done = True
                
    print("Q-Table after training (first 5 states):\n", agent.q_table[:5])

