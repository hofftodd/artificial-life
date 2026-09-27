import pygame
import random
import math
import sys

# Initialize pygame
pygame.init()

# Constants
WIDTH, HEIGHT = 800, 600
BACKGROUND_COLOR = (10, 10, 30)
ORGANISM_SIZE = 5
RADIATION_EMITTERS = 3
EMITTER_RANGE = 100
ENERGY_PER_RADIATION = 0.1
ENERGY_PER_EATING = 1.0
ENERGY_PER_MOVEMENT = 0.01
ENERGY_PER_SENSE = 0.005
MAX_ENERGY = 10.0
REPRODUCTION_ENERGY = 7.0
MUTATION_RATE = 0.1
MUTATION_AMOUNT = 0.2

# Create the screen
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Artificial Life Simulator")
clock = pygame.time.Clock()

class Gene:
    def __init__(self, absorption_spectrum=50, absorption_efficiency=1.0, 
                 stealing_ability=0.0, eating_ability=0.0, movement_ability=1.0,
                 radiation_sensing=1.0, organism_sensing=1.0):
        self.absorption_spectrum = absorption_spectrum  # Spectrum the organism is optimized for
        self.absorption_efficiency = absorption_efficiency  # How efficiently it absorbs radiation
        self.stealing_ability = stealing_ability  # Ability to steal energy from adjacent organisms
        self.eating_ability = eating_ability  # Ability to eat other organisms
        self.movement_ability = movement_ability  # Movement speed
        self.radiation_sensing = radiation_sensing  # Sensing range for radiation
        self.organism_sensing = organism_sensing  # Sensing range for other organisms
    
    def copy_with_mutation(self):
        # Create a copy with possible mutations
        new_spectrum = max(1, min(100, self.absorption_spectrum + random.gauss(0, MUTATION_AMOUNT * 100)))
        new_efficiency = max(0.1, min(2.0, self.absorption_efficiency + random.gauss(0, MUTATION_AMOUNT)))
        new_stealing = max(0.0, min(1.0, self.stealing_ability + random.gauss(0, MUTATION_AMOUNT)))
        new_eating = max(0.0, min(1.0, self.eating_ability + random.gauss(0, MUTATION_AMOUNT)))
        new_movement = max(0.1, min(2.0, self.movement_ability + random.gauss(0, MUTATION_AMOUNT)))
        new_radiation_sense = max(0.1, min(3.0, self.radiation_sensing + random.gauss(0, MUTATION_AMOUNT)))
        new_organism_sense = max(0.1, min(3.0, self.organism_sensing + random.gauss(0, MUTATION_AMOUNT)))
        
        return Gene(new_spectrum, new_efficiency, new_stealing, new_eating, new_movement,
                    new_radiation_sense, new_organism_sense)

class Emitter:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.spectrum = random.randint(1, 100)  # Random spectrum from 1-100
        
    def get_radiation_at(self, x, y):
        distance = math.sqrt((x - self.x)**2 + (y - self.y)**2)
        if distance < EMITTER_RANGE:
            # Radiation intensity decreases with distance
            intensity = 1.0 - (distance / EMITTER_RANGE)
            return intensity * ENERGY_PER_RADIATION
        return 0

class Organism:
    def __init__(self, x, y, genes=None):
        self.x = x
        self.y = y
        self.energy = random.uniform(2.0, 5.0)
        self.age = 0
        self.max_age = random.randint(1000, 3000)
        
        if genes is None:
            # Randomly generate genes for new organisms
            self.genes = Gene(
                absorption_spectrum=random.randint(1, 100),
                absorption_efficiency=random.uniform(0.5, 2.0),
                stealing_ability=random.uniform(0.0, 0.5),
                eating_ability=random.uniform(0.0, 0.5),
                movement_ability=random.uniform(0.5, 2.0),
                radiation_sensing=random.uniform(0.5, 2.0),
                organism_sensing=random.uniform(0.5, 2.0)
            )
        else:
            # Inherit genes with possible mutations
            self.genes = genes.copy_with_mutation()
            
        # Color based on absorption spectrum - red to blue gradient
        self.color = (
            min(255, int(self.genes.absorption_spectrum * 2.55)), 
            max(0, 255 - int(self.genes.absorption_spectrum * 2.55)), 
            100
        )
        self.original_color = self.color
        
    def update(self, emitters, organisms):
        self.age += 1
        
        # Absorb radiation from nearby emitters
        radiation_energy = 0
        for emitter in emitters:
            radiation_energy += emitter.get_radiation_at(self.x, self.y)
        
        # Apply absorption efficiency
        absorbed_energy = radiation_energy * self.genes.absorption_efficiency
        self.energy += absorbed_energy
        
        # Sense nearby radiation and move toward it
        closest_emitter = None
        closest_distance = float('inf')
        for emitter in emitters:
            distance = math.sqrt((self.x - emitter.x)**2 + (self.y - emitter.y)**2)
            if distance < closest_distance and distance < self.genes.radiation_sensing * 100:
                closest_emitter = emitter
                closest_distance = distance
        
        # Move toward closest emitter if found
        if closest_emitter and closest_distance > 5:
            dx = closest_emitter.x - self.x
            dy = closest_emitter.y - self.y
            distance = math.sqrt(dx**2 + dy**2)
            if distance > 0:
                self.x += (dx / distance) * self.genes.movement_ability * 0.5
                self.y += (dy / distance) * self.genes.movement_ability * 0.5
        
        # Sense and potentially steal energy from nearby organisms
        if self.genes.stealing_ability > 0:
            closest_target = None
            closest_distance = float('inf')
            for other in organisms:
                if other is not self:
                    distance = math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
                    if distance < closest_distance and distance < self.genes.organism_sensing * 50:
                        closest_target = other
                        closest_distance = distance
            
            if closest_target and closest_distance < 10:
                steal_amount = closest_target.energy * self.genes.stealing_ability
                if steal_amount > 0:
                    self.energy += steal_amount
                    closest_target.energy -= steal_amount
        
        # Sense and eat nearby organisms if we have eating ability
        if self.genes.eating_ability > 0:
            closest_target = None
            closest_distance = float('inf')
            for other in organisms:
                if other is not self and other.energy < 1.0:  # Only eat weak organisms
                    distance = math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)
                    if distance < closest_distance and distance < self.genes.organism_sensing * 50:
                        closest_target = other
                        closest_distance = distance
            
            if closest_target and closest_distance < 10:
                eat_amount = closest_target.energy * self.genes.eating_ability
                if eat_amount > 0:
                    self.energy += eat_amount
                    organisms.remove(closest_target)
        
        # Energy cost for movement, sensing, etc.
        self.energy -= ENERGY_PER_MOVEMENT * self.genes.movement_ability + ENERGY_PER_SENSE * self.genes.radiation_sensing
        
        # Reproduction if energy is sufficient
        if self.energy > REPRODUCTION_ENERGY and random.random() < 0.001:
            self.reproduce(organisms)
            
        # Die if energy is depleted or age exceeds max
        if self.energy <= 0 or self.age > self.max_age:
            return False
        return True
    
    def reproduce(self, organisms):
        # Create a new organism at a nearby location
        angle = random.uniform(0, 2 * math.pi)
        distance = random.uniform(0, 10)
        new_x = self.x + math.cos(angle) * distance
        new_y = self.y + math.sin(angle) * distance
        
        # Keep within bounds
        new_x = max(ORGANISM_SIZE, min(WIDTH - ORGANISM_SIZE, new_x))
        new_y = max(ORGANISM_SIZE, min(HEIGHT - ORGANISM_SIZE, new_y))
        
        # Create new organism with mutated genes
        new_organism = Organism(new_x, new_y, self.genes)
        organisms.append(new_organism)
        
        # Reduce parent's energy
        self.energy -= REPRODUCTION_ENERGY

# Create emitters
emitters = []
for _ in range(RADIATION_EMITTERS):
    emitters.append(Emitter(random.randint(50, WIDTH-50), random.randint(50, HEIGHT-50)))

# Create initial organisms
organisms = []
for _ in range(50):
    organisms.append(Organism(random.randint(50, WIDTH-50), random.randint(50, HEIGHT-50)))

# Main simulation loop
running = True
font = None
try:
    font = pygame.font.SysFont(None, 24)
except:
    pass

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
    
    # Update organisms
    organisms_to_remove = []
    for organism in organisms[:]:  # Create a copy for iteration
        if not organism.update(emitters, organisms):
            organisms_to_remove.append(organism)
    
    # Remove dead organisms
    for organism in organisms_to_remove:
        organisms.remove(organism)
    
    # Draw everything
    screen.fill(BACKGROUND_COLOR)
    
    # Draw emitters
    for emitter in emitters:
        pygame.draw.circle(screen, (255, 255, 255), (int(emitter.x), int(emitter.y)), 5)
        pygame.draw.circle(screen, (255, 255, 255), (int(emitter.x), int(emitter.y)), 10, 1)
    
    # Draw organisms
    for organism in organisms:
        # Change color based on energy level
        energy_ratio = max(0.2, min(1.0, organism.energy / MAX_ENERGY))
        r = int(organism.original_color[0] * energy_ratio)
        g = int(organism.original_color[1] * energy_ratio)
        b = int(organism.original_color[2] * energy_ratio)
        pygame.draw.circle(screen, (r, g, b), (int(organism.x), int(organism.y)), ORGANISM_SIZE)
    
    # Draw stats
    if font:
        stats_text = font.render(f"Organisms: {len(organisms)} | Emitters: {len(emitters)}", True, (255, 255, 255))
        screen.blit(stats_text, (10, 10))
    
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()