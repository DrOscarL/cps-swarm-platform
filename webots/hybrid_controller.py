"""
Hybrid ACO + Boredom Controller - VERSION 24 FIXED
CIBERFÍSICO + MODELO ENERGÉTICO VIRTUAL

Author: Oscar Loyola
Universidad de Las Américas - Chile
2025
"""

from controller import Supervisor
import numpy as np
import math
import os
import json
import socket

# ===== PARÁMETROS =====
NUM_ROBOTS = 5
TIME_STEP = 32
ARENA_SIZE = 5.0
GRID_SIZE = 25

NEST_POS = np.array([-2.0, 0.0])
FOOD_POS = np.array([2.0, 0.0])

# ACO
EVAPORATION_RATE = 0.995
PHEROMONE_DEPOSIT = 5.0
PHEROMONE_INIT = 0.1

# Boredom
BOREDOM_THRESHOLD = 0.3
INTRINSIC_WEIGHT = 1.5

# Movimiento
ARRIVAL_THRESHOLD = 0.3
STEP_SIZE = 0.05

# Evasión
COLLISION_DISTANCE = 0.15
AVOIDANCE_STRENGTH = 0.3

# Energía (modelo e-puck)
BATTERY_CAPACITY_mAh = 1000.0
CURRENT_BASE_mA = 50.0          # Consumo base
CURRENT_MOTOR_mA = 100.0        # Consumo por movimiento
CURRENT_SENSOR_mA = 10.0        # Consumo sensores
RECHARGE_RATE_mA = 200.0        # Recarga en el nido

ENERGY_CRITICAL = 20.0          # % crítico
ENERGY_LOW = 50.0               # % bajo

# Simulación
MAX_ITERATIONS = 5000

# ===== CONFIGURACIÓN NODEMCU =====
NODEMCU_CONFIG = [
    {'ip': '172.20.10.3', 'port': 8080, 'robot_id': 0},
    {'ip': '172.20.10.2', 'port': 8080, 'robot_id': 1},
    {'ip': '172.20.10.4', 'port': 8080, 'robot_id': 3},
    {'ip': '172.20.10.6', 'port': 8080, 'robot_id': 4}
]
WIFI_ENABLED = True


class ChuaOscillator:
    def __init__(self):
        self.x = 0.1 + np.random.random() * 0.2
        self.y = 0.1 + np.random.random() * 0.1
        self.z = 0.1
    
    def update(self):
        m0, m1 = -1.143, -0.714
        f_x = m1 * self.x + 0.5 * (m0 - m1) * (abs(self.x + 1) - abs(self.x - 1))
        h = 0.01
        self.x += h * (15.6 * (self.y - self.x - f_x))
        self.y += h * (self.x - self.y + self.z)
        self.z += h * (-28.0 * self.y - 1.143 * self.z)
        return abs(self.z)


class Agent:
    def __init__(self, i):
        self.id = i
        self.state = 'SEARCHING'
        self.chua = ChuaOscillator()
        self.boredom_active = False
        self.target = None
        self.food = 0
        self.preferred_angle = np.random.uniform(0, 2 * np.pi)
        self.trajectory = []
        
        # Energía
        self.battery_mAh = BATTERY_CAPACITY_mAh
        self.energy_consumed_mAh = 0.0
        self.distance_traveled = 0.0
        self.last_pos = None
        self.energy_emergency = False


class HybridSwarmController(Supervisor):
    def __init__(self):
        super().__init__()
        
        self.nodes = []
        self.trans = []
        self.rot = []
        
        for i in range(NUM_ROBOTS):
            node = self.getFromDef(f'ROBOT_{i}')
            if node:
                self.nodes.append(node)
                self.trans.append(node.getField('translation'))
                self.rot.append(node.getField('rotation'))
                pos = self.trans[-1].getSFVec3f()
                print(f"✓ ROBOT_{i} at ({pos[0]:.2f}, {pos[1]:.2f})")
        
        self.agents = [Agent(i) for i in range(len(self.nodes))]
        self.pheromones = np.ones((GRID_SIZE, GRID_SIZE)) * PHEROMONE_INIT
        self.iter = 0
        
        # Temperatura por robot
        self.robot_temperatures = {i: 25.0 for i in range(NUM_ROBOTS)}
        
        # Historial
        self.history = {
            'iterations': [],
            'food_collected': [],
            'boredom_count': [],
            'returning_count': [],
            'max_pheromone': [],
            'avg_pheromone': [],
            'pheromone_snapshots': [],
            'temperatures': [],
            'battery_levels': [],
            'energy_consumed': [],
            'distance_traveled': [],
            'energy_efficiency': [],
            'energy_per_food': [],
        }
        
        # ===== CONEXIONES TCP =====
        self.nodemcu_sockets = {}
        if WIFI_ENABLED:
            self._connect_all_nodemcu()
        
        print(f"\n{'='*50}")
        print(f"HYBRID SWARM v24 - Modelo Energético")
        print(f"Robots: {len(self.nodes)}")
        print(f"NodeMCU conectados: {len(self.nodemcu_sockets)}")
        print(f"{'='*50}\n")
    
    def _connect_all_nodemcu(self):
        """Conectar a todos los NodeMCU"""
        for config in NODEMCU_CONFIG:
            robot_id = config['robot_id']
            ip = config['ip']
            port = config['port']
            
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect((ip, port))
                sock.setblocking(False)
                self.nodemcu_sockets[robot_id] = sock
                print(f"✓ NodeMCU Robot {robot_id}: {ip}:{port}")
            except Exception as e:
                print(f"⚠️ NodeMCU Robot {robot_id} ({ip}): {e}")
    
    def _send_to_nodemcu(self, robot_id, data):
        """Enviar datos al NodeMCU de un robot específico"""
        if robot_id in self.nodemcu_sockets:
            try:
                msg = json.dumps(data) + '\n'
                self.nodemcu_sockets[robot_id].sendall(msg.encode())
            except:
                pass
    
    def _receive_from_nodemcu(self, robot_id):
        """Recibir datos del NodeMCU (temperatura)"""
        if robot_id in self.nodemcu_sockets:
            try:
                sock = self.nodemcu_sockets[robot_id]
                data = sock.recv(256).decode()
                
                for line in data.strip().split('\n'):
                    if line:
                        try:
                            msg = json.loads(line)
                            if 'temp' in msg:
                                self.robot_temperatures[robot_id] = msg['temp']
                        except:
                            pass
            except:
                pass
    
    def _get_temperature_factor(self, robot_id):
        """Calcular factores de velocidad y boredom según temperatura"""
        temp = self.robot_temperatures.get(robot_id, 25.0)
        
        if temp < 15:
            speed_factor = 0.5 + (temp / 30)
            boredom_factor = 0.8
        elif temp > 35:
            speed_factor = 1.0 + ((temp - 35) / 30)
            boredom_factor = 1.5
        else:
            speed_factor = 1.0
            boredom_factor = 1.0
        
        return speed_factor, boredom_factor
    
    def _get_energy_factor(self, robot_id):
        """Calcular factores según nivel de batería (HOMEOSTASIS)"""
        agent = self.agents[robot_id]
        battery_percent = (agent.battery_mAh / BATTERY_CAPACITY_mAh) * 100.0
        
        if battery_percent < ENERGY_CRITICAL:
            speed_factor = 0.5  # No tan lento, para que siga moviéndose
            boredom_factor = 0.0
            can_explore = False
        elif battery_percent < ENERGY_LOW:
            speed_factor = 0.8  # Conservador pero funcional
            boredom_factor = 0.5
            can_explore = True
        else:
            speed_factor = 1.0
            boredom_factor = 1.0
            can_explore = True
        
        return speed_factor, boredom_factor, can_explore
    
    def _calculate_energy_consumption(self, i, distance_moved):
        """Calcular consumo energético del robot"""
        agent = self.agents[i]
        pos = self._get_pos(i)
        
        # Tiempo en horas
        time_h = TIME_STEP / (1000.0 * 3600.0)
        
        # 1. Consumo base
        base_consumption = CURRENT_BASE_mA * time_h
        
        # 2. Consumo por movimiento
        movement_consumption = CURRENT_MOTOR_mA * distance_moved * 10 * time_h  # Factor 10 para escalar
        
        # 3. Consumo sensores (solo cuando no está en nido)
        dist_nest = np.linalg.norm(pos - NEST_POS)
        if dist_nest > ARRIVAL_THRESHOLD:
            sensor_consumption = CURRENT_SENSOR_mA * time_h
        else:
            sensor_consumption = 0.0
        
        total_consumption = base_consumption + movement_consumption + sensor_consumption
        
        # Actualizar batería
        agent.battery_mAh -= total_consumption
        agent.energy_consumed_mAh += total_consumption
        
        # Recarga en el nido
        if dist_nest < ARRIVAL_THRESHOLD and agent.battery_mAh < BATTERY_CAPACITY_mAh:
            recharge = RECHARGE_RATE_mA * time_h
            agent.battery_mAh = min(agent.battery_mAh + recharge, BATTERY_CAPACITY_mAh)
        
        # Calcular porcentaje
        battery_percent = (agent.battery_mAh / BATTERY_CAPACITY_mAh) * 100.0
        
        # Estado de emergencia
        if battery_percent < ENERGY_CRITICAL:
            agent.energy_emergency = True
        elif battery_percent > ENERGY_LOW:
            agent.energy_emergency = False
        
        return battery_percent
    
    def _get_pos(self, i):
        t = self.trans[i].getSFVec3f()
        return np.array([t[0], t[1]])
    
    def _get_all_positions(self):
        return [self._get_pos(i) for i in range(len(self.nodes))]
    
    def _pos_to_grid(self, pos):
        gx = int((pos[0] + ARENA_SIZE/2) / ARENA_SIZE * GRID_SIZE)
        gy = int((pos[1] + ARENA_SIZE/2) / ARENA_SIZE * GRID_SIZE)
        return (np.clip(gx, 0, GRID_SIZE-1), np.clip(gy, 0, GRID_SIZE-1))
    
    def _is_valid_pos(self, pos):
        margin = 0.15
        return (abs(pos[0]) < ARENA_SIZE/2 - margin and 
                abs(pos[1]) < ARENA_SIZE/2 - margin)
    
    def _calculate_avoidance(self, i, current_pos):
        avoidance = np.array([0.0, 0.0])
        all_pos = self._get_all_positions()
        
        for j, other_pos in enumerate(all_pos):
            if i == j:
                continue
            diff = current_pos - other_pos
            dist = np.linalg.norm(diff)
            if dist < COLLISION_DISTANCE and dist > 0.01:
                repulsion = (diff / dist) * (COLLISION_DISTANCE - dist) / COLLISION_DISTANCE
                avoidance += repulsion
        
        return avoidance * AVOIDANCE_STRENGTH
    
    def _move(self, i, target):
        agent = self.agents[i]
        pos = self._get_pos(i)
        
        # Guardar posición anterior para calcular distancia
        if agent.last_pos is None:
            agent.last_pos = pos.copy()
        
        diff = target - pos
        dist = np.linalg.norm(diff)
        
        if dist < ARRIVAL_THRESHOLD:
            return True
        
        direction = diff / dist
        avoidance = self._calculate_avoidance(i, pos)
        final_direction = direction + avoidance
        norm = np.linalg.norm(final_direction)
        if norm > 0:
            final_direction = final_direction / norm
        
        # Aplicar factores de temperatura Y energía
        temp_speed, _ = self._get_temperature_factor(i)
        energy_speed, _, _ = self._get_energy_factor(i)
        
        # Combinar factores (promedio ponderado en lugar de mínimo)
        final_speed = (temp_speed * 0.6 + energy_speed * 0.4)
        adjusted_step = STEP_SIZE * final_speed
        
        new = pos + final_direction * adjusted_step
        new[0] = np.clip(new[0], -ARENA_SIZE/2 + 0.15, ARENA_SIZE/2 - 0.15)
        new[1] = np.clip(new[1], -ARENA_SIZE/2 + 0.15, ARENA_SIZE/2 - 0.15)
        
        # Calcular distancia movida
        distance_moved = np.linalg.norm(new - agent.last_pos)
        agent.distance_traveled += distance_moved
        
        # Calcular consumo energético
        self._calculate_energy_consumption(i, distance_moved)
        
        agent.last_pos = new.copy()
        
        self.trans[i].setSFVec3f([float(new[0]), float(new[1]), 0.0])
        
        if np.linalg.norm(final_direction) > 0.02:
            angle = math.atan2(final_direction[1], final_direction[0])
            self.rot[i].setSFRotation([0, 0, 1, angle])
        
        self.nodes[i].resetPhysics()
        return False
    
    def _decide_target(self, i):
        agent = self.agents[i]
        pos = self._get_pos(i)
        
        # EMERGENCIA ENERGÉTICA: Volver al nido inmediatamente
        if agent.energy_emergency and agent.state == 'SEARCHING':
            agent.state = 'RETURNING'
            return NEST_POS.copy()
        
        if agent.state == 'RETURNING':
            return NEST_POS.copy()
        
        grid_pos = self._pos_to_grid(pos)
        current_pheromone = self.pheromones[grid_pos[0], grid_pos[1]]
        intrinsic = agent.chua.update()
        
        # Modificar umbral por temperatura Y energía
        _, temp_boredom = self._get_temperature_factor(i)
        _, energy_boredom, can_explore = self._get_energy_factor(i)
        
        # Combinar factores
        combined_boredom = min(temp_boredom, energy_boredom)
        adjusted_threshold = BOREDOM_THRESHOLD * combined_boredom
        
        # Si no puede explorar, forzar explotación
        if not can_explore:
            agent.boredom_active = False
            target = self._follow_pheromone_away_from_nest(pos)
        elif current_pheromone > adjusted_threshold:
            agent.boredom_active = False
            target = self._follow_pheromone_away_from_nest(pos)
        else:
            agent.boredom_active = True
            target = self._explore_with_boredom(i, pos, intrinsic)
        
        return target
    
    def _follow_pheromone_away_from_nest(self, pos):
        best_target = None
        best_score = -1
        
        away_from_nest = pos - NEST_POS
        away_norm = np.linalg.norm(away_from_nest)
        if away_norm > 0:
            away_from_nest = away_from_nest / away_norm
        
        for angle in np.linspace(0, 2*np.pi, 12, endpoint=False):
            direction = np.array([np.cos(angle), np.sin(angle)])
            test_pos = pos + direction * 0.3
            
            if not self._is_valid_pos(test_pos):
                continue
            
            dot_product = np.dot(direction, away_from_nest)
            if dot_product < -0.3:
                continue
            
            grid = self._pos_to_grid(test_pos)
            pheromone = self.pheromones[grid[0], grid[1]]
            score = pheromone + dot_product * 0.5 + np.random.random() * 0.2
            
            if score > best_score:
                best_score = score
                best_target = test_pos
        
        if best_target is None:
            angle = np.random.uniform(0, 2*np.pi)
            best_target = pos + np.array([np.cos(angle), np.sin(angle)]) * 0.3
            best_target[0] = np.clip(best_target[0], -ARENA_SIZE/2 + 0.2, ARENA_SIZE/2 - 0.2)
            best_target[1] = np.clip(best_target[1], -ARENA_SIZE/2 + 0.2, ARENA_SIZE/2 - 0.2)
        
        return best_target
    
    def _explore_with_boredom(self, i, pos, intrinsic):
        agent = self.agents[i]
        agent.preferred_angle += (intrinsic - 0.5) * 0.3
        
        away_from_nest = pos - NEST_POS
        away_angle = math.atan2(away_from_nest[1], away_from_nest[0])
        final_angle = agent.preferred_angle * 0.7 + away_angle * 0.3
        
        direction = np.array([np.cos(final_angle), np.sin(final_angle)])
        target = pos + direction * 0.5
        
        if not self._is_valid_pos(target):
            agent.preferred_angle += np.pi/2 + np.random.uniform(-0.3, 0.3)
            direction = np.array([np.cos(agent.preferred_angle), np.sin(agent.preferred_angle)])
            target = pos + direction * 0.5
        
        target[0] = np.clip(target[0], -ARENA_SIZE/2 + 0.2, ARENA_SIZE/2 - 0.2)
        target[1] = np.clip(target[1], -ARENA_SIZE/2 + 0.2, ARENA_SIZE/2 - 0.2)
        
        return target
    
    def _update_state(self, i):
        agent = self.agents[i]
        pos = self._get_pos(i)
        grid = self._pos_to_grid(pos)
        agent.trajectory.append(pos.copy())
        
        dist_food = np.linalg.norm(pos - FOOD_POS)
        dist_nest = np.linalg.norm(pos - NEST_POS)
        
        if agent.state == 'SEARCHING' and dist_food < ARRIVAL_THRESHOLD:
            agent.state = 'RETURNING'
            agent.food += 1
            agent.target = None
            battery_percent = (agent.battery_mAh / BATTERY_CAPACITY_mAh) * 100.0
            print(f"  🍎 Robot {i} found FOOD! (Total: {agent.food}, Bat: {battery_percent:.1f}%)")
            
            self._send_to_nodemcu(i, {
                'evt': 'FOOD',
                't': agent.food
            })
            
        elif agent.state == 'RETURNING':
            self.pheromones[grid[0], grid[1]] += PHEROMONE_DEPOSIT
            
            if dist_nest < ARRIVAL_THRESHOLD:
                agent.state = 'SEARCHING'
                agent.target = None
                agent.preferred_angle = np.random.uniform(0, 2*np.pi)
                agent.energy_emergency = False
                print(f"  🏠 Robot {i} returned to NEST")
                
                self._send_to_nodemcu(i, {'evt': 'NEST'})
    
    def _record_metrics(self):
        self.history['iterations'].append(self.iter)
        self.history['food_collected'].append(sum(a.food for a in self.agents))
        self.history['boredom_count'].append(sum(1 for a in self.agents if a.boredom_active))
        self.history['returning_count'].append(sum(1 for a in self.agents if a.state == 'RETURNING'))
        self.history['max_pheromone'].append(np.max(self.pheromones))
        self.history['avg_pheromone'].append(np.mean(self.pheromones))
        
        # Temperaturas
        temps = [self.robot_temperatures.get(i, 25.0) for i in range(len(self.nodes))]
        self.history['temperatures'].append(temps)
        
        # Batería
        batteries = [(a.battery_mAh / BATTERY_CAPACITY_mAh) * 100.0 for a in self.agents]
        self.history['battery_levels'].append(batteries)
        
        # Energía consumida
        energies = [a.energy_consumed_mAh for a in self.agents]
        self.history['energy_consumed'].append(energies)
        
        # Distancia recorrida
        distances = [a.distance_traveled for a in self.agents]
        self.history['distance_traveled'].append(distances)
        
        # Eficiencia energética
        total_food = sum(a.food for a in self.agents)
        total_energy = sum(a.energy_consumed_mAh for a in self.agents)
        
        if total_energy > 0:
            efficiency = total_food / total_energy
            energy_per_food = total_energy / max(total_food, 1)
        else:
            efficiency = 0
            energy_per_food = 0
        
        self.history['energy_efficiency'].append(efficiency)
        self.history['energy_per_food'].append(energy_per_food)
        
        if self.iter % 500 == 0:
            self.history['pheromone_snapshots'].append({
                'iter': self.iter,
                'map': self.pheromones.copy()
            })
    
    def _send_robot_status(self):
        """Enviar estado de cada robot a su NodeMCU"""
        for i in range(len(self.nodes)):
            if i not in self.nodemcu_sockets:
                continue
            
            pos = self._get_pos(i)
            agent = self.agents[i]
            
            grid_pos = self._pos_to_grid(pos)
            current_pheromone = self.pheromones[grid_pos[0], grid_pos[1]]
            
            dist_food = round(np.linalg.norm(pos - FOOD_POS), 2)
            dist_nest = round(np.linalg.norm(pos - NEST_POS), 2)
            
            battery_percent = (agent.battery_mAh / BATTERY_CAPACITY_mAh) * 100.0
            
            data = {
                'i': self.iter,
                'x': round(pos[0], 2),
                'y': round(pos[1], 2),
                's': agent.state,
                'b': agent.boredom_active,
                'f': agent.food,
                'df': dist_food,
                'dn': dist_nest,
                'p': round(current_pheromone, 2),
                'bat': round(battery_percent, 1),
                'energy': round(agent.energy_consumed_mAh, 2),
                'e': agent.energy_emergency
            }
            
            self._send_to_nodemcu(i, data)
    
    def _generate_plots(self):
        try:
            import matplotlib.pyplot as plt
            
            output_dir = "simulation_results"
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
            
            # 1. Comida recolectada
            plt.figure(figsize=(10, 6))
            plt.plot(self.history['iterations'], self.history['food_collected'], 'b-', linewidth=2)
            plt.xlabel('Iteraciones')
            plt.ylabel('Comida Recolectada')
            plt.title('Eficiencia de Recolección - ACO + Boredom + Energía')
            plt.grid(True)
            plt.savefig(f"{output_dir}/food_collected.png", dpi=150)
            plt.close()
            
            # 2. Boredom
            plt.figure(figsize=(10, 6))
            plt.plot(self.history['boredom_count'], 'r-', linewidth=2)
            plt.xlabel('Iteraciones (x10)')
            plt.ylabel('Robots con Boredom Activo')
            plt.title('Activación de Motivación Intrínseca')
            plt.grid(True)
            plt.savefig(f"{output_dir}/boredom_activation.png", dpi=150)
            plt.close()
            
            # 3. Feromonas
            plt.figure(figsize=(10, 6))
            plt.plot(self.history['iterations'], self.history['max_pheromone'], 'g-', label='Máximo', linewidth=2)
            plt.plot(self.history['iterations'], self.history['avg_pheromone'], 'g--', label='Promedio', linewidth=1)
            plt.xlabel('Iteraciones')
            plt.ylabel('Nivel de Feromona')
            plt.title('Evolución de Feromonas')
            plt.legend()
            plt.grid(True)
            plt.savefig(f"{output_dir}/pheromone_levels.png", dpi=150)
            plt.close()
            
            # 4. Heatmaps de feromonas
            n_snapshots = len(self.history['pheromone_snapshots'])
            if n_snapshots > 0:
                cols = min(3, n_snapshots)
                rows = (n_snapshots + cols - 1) // cols
                fig, axes = plt.subplots(rows, cols, figsize=(5*cols, 5*rows))
                if n_snapshots == 1:
                    axes = [axes]
                else:
                    axes = axes.flatten()
                
                for idx, snapshot in enumerate(self.history['pheromone_snapshots']):
                    if idx < len(axes):
                        im = axes[idx].imshow(snapshot['map'], cmap='hot', origin='lower')
                        axes[idx].set_title(f"Iter {snapshot['iter']}")
                        plt.colorbar(im, ax=axes[idx])
                
                for idx in range(n_snapshots, len(axes)):
                    axes[idx].axis('off')
                
                plt.tight_layout()
                plt.savefig(f"{output_dir}/pheromone_heatmaps.png", dpi=150)
                plt.close()
            
            # 5. Trayectorias
            plt.figure(figsize=(10, 10))
            colors = ['blue', 'red', 'green', 'orange', 'purple']
            
            for i, agent in enumerate(self.agents):
                if len(agent.trajectory) > 0:
                    traj = np.array(agent.trajectory)
                    plt.plot(traj[:, 0], traj[:, 1], '-', color=colors[i % len(colors)], 
                            alpha=0.5, linewidth=0.5, label=f'Robot {i}')
            
            plt.plot(NEST_POS[0], NEST_POS[1], 'bs', markersize=15, label='Nido')
            plt.plot(FOOD_POS[0], FOOD_POS[1], 'g^', markersize=15, label='Comida')
            
            plt.xlabel('X')
            plt.ylabel('Y')
            plt.title('Trayectorias de Robots')
            plt.legend()
            plt.axis('equal')
            plt.grid(True)
            plt.savefig(f"{output_dir}/trajectories.png", dpi=150)
            plt.close()
            
            # 6. Temperaturas
            if self.history['temperatures']:
                plt.figure(figsize=(10, 6))
                temps_array = np.array(self.history['temperatures'])
                for i in range(min(temps_array.shape[1], NUM_ROBOTS)):
                    plt.plot(self.history['iterations'], temps_array[:, i], 
                            label=f'Robot {i}', linewidth=1)
                plt.xlabel('Iteraciones')
                plt.ylabel('Temperatura (°C)')
                plt.title('Temperatura Ambiental por Robot')
                plt.legend()
                plt.grid(True)
                plt.savefig(f"{output_dir}/temperatures.png", dpi=150)
                plt.close()
            
            # 7. Batería
            if self.history['battery_levels']:
                plt.figure(figsize=(10, 6))
                batt_array = np.array(self.history['battery_levels'])
                for i in range(min(batt_array.shape[1], NUM_ROBOTS)):
                    plt.plot(self.history['iterations'], batt_array[:, i], 
                            label=f'Robot {i}', linewidth=1)
                plt.axhline(y=ENERGY_CRITICAL, color='r', linestyle='--', label='Crítico', alpha=0.5)
                plt.axhline(y=ENERGY_LOW, color='orange', linestyle='--', label='Bajo', alpha=0.5)
                plt.xlabel('Iteraciones')
                plt.ylabel('Batería (%)')
                plt.title('Nivel de Batería por Robot (Homeostasis Energética)')
                plt.legend()
                plt.grid(True)
                plt.ylim(0, 105)
                plt.savefig(f"{output_dir}/battery_levels.png", dpi=150)
                plt.close()
            
            # 8. Distancia recorrida
            if self.history['distance_traveled']:
                plt.figure(figsize=(10, 6))
                dist_array = np.array(self.history['distance_traveled'])
                for i in range(min(dist_array.shape[1], NUM_ROBOTS)):
                    plt.plot(self.history['iterations'], dist_array[:, i], 
                            label=f'Robot {i}', linewidth=1)
                plt.xlabel('Iteraciones')
                plt.ylabel('Distancia (m)')
                plt.title('Distancia Recorrida por Robot')
                plt.legend()
                plt.grid(True)
                plt.savefig(f"{output_dir}/distance_traveled.png", dpi=150)
                plt.close()
            
            # 9. Eficiencia energética
            if self.history['energy_efficiency']:
                plt.figure(figsize=(10, 6))
                plt.plot(self.history['iterations'], self.history['energy_efficiency'], 
                        'purple', linewidth=2)
                plt.xlabel('Iteraciones')
                plt.ylabel('Eficiencia (Comida/mAh)')
                plt.title('Eficiencia Energética del Swarm')
                plt.grid(True)
                plt.savefig(f"{output_dir}/energy_efficiency.png", dpi=150)
                plt.close()
            
            # 10. Energía por comida
            if self.history['energy_per_food']:
                plt.figure(figsize=(10, 6))
                plt.plot(self.history['iterations'], self.history['energy_per_food'], 
                        'brown', linewidth=2)
                plt.xlabel('Iteraciones')
                plt.ylabel('Energía (mAh/Comida)')
                plt.title('Costo Energético por Unidad de Comida')
                plt.grid(True)
                plt.savefig(f"{output_dir}/energy_per_food.png", dpi=150)
                plt.close()
            
            print(f"\n📊 Gráficas guardadas en '{output_dir}/'")
            
        except ImportError:
            print("\n⚠️ matplotlib no instalado")
        except Exception as e:
            print(f"\n⚠️ Error generando gráficas: {e}")
    
    def run(self):
        print("Starting...\n")
        
        while self.step(TIME_STEP) != -1:
            self.iter += 1
            
            # Recibir temperatura de cada NodeMCU
            for robot_id in self.nodemcu_sockets:
                self._receive_from_nodemcu(robot_id)
            
            for i in range(len(self.nodes)):
                agent = self.agents[i]
                
                if agent.target is None or self.iter % 3 == 0:
                    agent.target = self._decide_target(i)
                
                if agent.target is not None:
                    if self._move(i, agent.target):
                        agent.target = None
                
                self._update_state(i)
            
            self.pheromones *= EVAPORATION_RATE
            self.pheromones = np.clip(self.pheromones, PHEROMONE_INIT, 100)
            
            if self.iter % 10 == 0:
                self._record_metrics()
            
            # Enviar estado a cada NodeMCU
            if self.iter % 30 == 0:
                self._send_robot_status()
            
            if self.iter % 200 == 0:
                ret = sum(1 for a in self.agents if a.state == 'RETURNING')
                bor = sum(1 for a in self.agents if a.boredom_active)
                food = sum(a.food for a in self.agents)
                avg_bat = np.mean([(a.battery_mAh / BATTERY_CAPACITY_mAh) * 100 for a in self.agents])
                print(f"Iter {self.iter:5d} | Ret: {ret} | Bored: {bor} | Food: {food} | Bat: {avg_bat:.1f}%")
            
            if self.iter >= MAX_ITERATIONS:
                print(f"\n{'='*50}")
                print(f"FIN - Total Comida: {sum(a.food for a in self.agents)}")
                total_energy = sum(a.energy_consumed_mAh for a in self.agents)
                print(f"Energía consumida: {total_energy:.1f} mAh")
                if total_energy > 0:
                    print(f"Eficiencia: {sum(a.food for a in self.agents) / total_energy:.4f} Comida/mAh")
                print(f"{'='*50}")
                self._generate_plots()
                
                for sock in self.nodemcu_sockets.values():
                    sock.close()
                break


if __name__ == '__main__':
    HybridSwarmController().run()
