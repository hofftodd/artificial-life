#!/usr/bin/env python3
"""
Artificial Life Simulator
========================

This simulator demonstrates artificial organisms that evolve through genetic inheritance
and mutations. The organisms are designed to:
- Absorb radiation for energy
- Reproduce asexually with genetic mutations
- Adapt to different radiation spectrums
- Steal energy from nearby organisms
- Eat weaker organisms
- Move toward radiation sources
"""

import random
import math
import time

class Gene:
    """Represents genetic traits of an organism"""
    def __init__(self, absorption_spectrum=50, absorption_efficiency=1.0, 
                 stealing_ability=0.0, eating_ability=0.0, movement_ability=1.0,
                 radiation_sensing=1.0, organism_sensing=1.0):
        self.absorption_spectrum = absorption_spectrum  # Spectrum the organism is optimized for (1-100)
        self.absorption_efficiency = absorption_efficiency  # How efficiently it absorbs radiation
        self.stealing_ability = stealing_ability  # Ability to steal energy from adjacent organisms
        self.eating_ability = eating_ability  # Ability to eat other organisms
        self.movement_ability = movement_ability  # Movement speed
        self.radiation_sensing = radiation_sensing  # Sensing range for radiation
        self.organism_sensing = organism_sensing  # Sensing range for other organisms
    
    def copy_with_mutation(self):
        """Create a copy with possible mutations"""
        new_spectrum = max(1, min(100, self.absorption_spectrum + random.gauss(0, 10)))
        new_efficiency = max(0.1, min(2.0, self.absorption_efficiency + random.gauss(0, 0.2)))
        new_stealing = max(0.0, min(1.0, self.stealing_ability + random.gauss(0, 0.1)))
        new_eating = max(0.0, min(1.0, self.eating_ability + random.gauss(0, 0.1)))
        new_movement = max(0.1, min(2.0, self.movement_ability + random.gauss(0, 0.1)))
        new_radiation_sense = max(0.1, min(3.0, self.radiation_sensing + random.gauss(0, 0.1)))
        new_organism_sense = max(0.1, min(3.0, self.organism_sensing + random.gauss(0, 0.1)))
        
        return Gene(new_spectrum, new_efficiency, new_stealing, new_eating, new_movement,
                    new_radiation_sense, new_organism_sense)

class Emitter:
    """Radiation emitter that generates radiation in a specific spectrum"""
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.spectrum = random.randint(1, 100)  # Random spectrum from 1-100
        
    def get_radiation_at(self, x, y):
        """Calculate radiation intensity at position (x,y)"""
        distance = math.sqrt((x - self.x)**2 + (y - self.y)**2)
        if distance < 100:  # Emitter range
            # Radiation intensity decreases with distance
            intensity = 1.0 - (distance / 100)
            return intensity * 0.1  # Base energy from radiation
        return 0

class Organism:
    """Single-celled artificial organism"""
    def __init__(self, x, y, genes=None):
        self.x = x
        self.y = y
        self.energy = random.uniform(2.0, 5.0)
        self.age = 0
        self.max_age = random.randint(1000, 3000)
        self.id = random.randint(10000, 99999)
        
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
            
        # Color based on absorption spectrum (for visualization)
        self.color = f"RGB({int(self.genes.absorption_spectrum * 2.55)}, {255 - int(self.genes.absorption_spectrum * 2.55)}, 100)"
        
    def absorb_radiation(self, emitters):
        """Absorb radiation from nearby emitters"""
        radiation_energy = 0
        for emitter in emitters:
            radiation_energy += emitter.get_radiation_at(self.x, self.y)
        
        # Apply absorption efficiency
        absorbed_energy = radiation_energy * self.genes.absorption_efficiency
        self.energy += absorbed_energy
        return absorbed_energy
    
    def sense_and_move(self, emitters):
        """Sense nearby radiation and move toward it"""
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
    
    def steal_from_neighbors(self, organisms):
        """Attempt to steal energy from nearby organisms"""
        if self.genes.stealing_ability <= 0:
            return 0
            
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
                return steal_amount
        return 0
    
    def eat_neighbors(self, organisms):
        """Attempt to eat nearby weaker organisms"""
        if self.genes.eating_ability <= 0:
            return 0
            
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
                return eat_amount
        return 0
    
    def update(self, emitters, organisms):
        """Update organism state"""
        self.age += 1
        
        # Absorb radiation
        radiation_energy = self.absorb_radiation(emitters)
        
        # Sense and move toward radiation
        self.sense_and_move(emitters)
        
        # Steal from neighbors
        steal_amount = self.steal_from_neighbors(organisms)
        
        # Eat neighbors
        eat_amount = self.eat_neighbors(organisms)
        
        # Energy cost for movement and sensing
        self.energy -= 0.01 * self.genes.movement_ability + 0.005 * self.genes.radiation_sensing
        
        # Reproduction if energy is sufficient
        reproduction_energy = 7.0
        if self.energy > reproduction_energy and random.random() < 0.001:
            return self.reproduce(organisms)
            
        # Die if energy is depleted or age exceeds max
        if self.energy <= 0 or self.age > self.max_age:
            return False
        return True
    
    def reproduce(self, organisms):
        """Create a new organism with mutated genes"""
        # Create a new organism at a nearby location
        angle = random.uniform(0, 2 * math.pi)
        distance = random.uniform(0, 10)
        new_x = self.x + math.cos(angle) * distance
        new_y = self.y + math.sin(angle) * distance
        
        # Keep within bounds (simplified)
        new_x = max(0, min(100, new_x))
        new_y = max(0, min(100, new_y))
        
        # Create new organism with mutated genes
        new_organism = Organism(new_x, new_y, self.genes)
        organisms.append(new_organism)
        
        # Reduce parent's energy
        self.energy -= 7.0
        return True

def simulate():
    """Run the artificial life simulation"""
    print("Artificial Life Simulator")
    print("=" * 50)
    print("Simulating single-celled organisms with genetic evolution")
    print()
    
    # Create emitters
    emitters = []
    for i in range(3):
        emitters.append(Emitter(random.randint(10, 90), random.randint(10, 90)))
    
    # Create initial organisms
    organisms = []
    for i in range(20):
        organisms.append(Organism(random.randint(10, 90), random.randint(10, 90)))
    
    print(f"Initial organisms: {len(organisms)}")
    print(f"Emitters: {len(emitters)}")
    print()
    
    # Simulation loop
    for generation in range(100):
        print(f"Generation {generation + 1}")
        
        # Update all organisms
        organisms_to_remove = []
        for organism in organisms[:]:  # Create a copy for iteration
            if not organism.update(emitters, organisms):
                organisms_to_remove.append(organism)
        
        # Remove dead organisms
        for organism in organisms_to_remove:
            organisms.remove(organism)
        
        # Print stats for this generation
        if generation % 10 == 0:  # Print every 10 generations
            print(f"  Organisms: {len(organisms)}")
            
            # Show some statistics about the organisms
            if organisms:
                avg_spectrum = sum(o.genes.absorption_spectrum for o in organisms) / len(organisms)
                avg_efficiency = sum(o.genes.absorption_efficiency for o in organisms) / len(organisms)
                print(f"  Average absorption spectrum: {avg_spectrum:.1f}")
                print(f"  Average absorption efficiency: {avg_efficiency:.2f}")
        
        time.sleep(0.1)  # Pause for visualization
    
    print()
    print("Simulation complete!")
    print(f"Final population: {len(organisms)} organisms")

if __name__ == "__main__":
    simulate()