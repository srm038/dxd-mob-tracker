import shlex
import dice
from dataclasses import dataclass, field
from textual.app import App, ComposeResult
from textual import events
from textual.widgets import Header, Footer, RichLog, Input, Static
from textual.containers import Vertical, Horizontal

@dataclass
class Mob:
    name: str
    max_hp: int
    hp: int = field(init=False)
    status: str = "Alive"
    stunned: bool = False
    morale: int = 7  # Default morale rating (7 for clan fighters, etc.)
    morale_status: str = "Normal"  # Normal, Panicked, Routed
    min_hp: int = 0  # Minimum HP before mob is killed (can be negative for certain mobs)

    def __post_init__(self):
        self.hp = self.max_hp

@dataclass
class PC:
    name: str
    max_hp: int
    hp: int = field(init=False)
    status: str = "Alive"
    stunned: bool = False
    morale: int = 9  # Default morale for PCs
    morale_status: str = "Normal"  # Normal, Panicked, Routed
    min_hp: int = -10  # PCs can survive with negative HP up to -10
    damage_dealt: int = 0  # Total damage dealt by this PC
    damage_taken: int = 0  # Total damage taken by this PC
    xp_damage_taken: int = 0  # XP earned from damage taken (20 XP per HP)
    xp_damage_dealt: int = 0  # XP earned from damage dealt (10 XP per HP)
    xp_bonus: int = 0  # Bonus XP from party damage taken
    total_xp: int = 0  # Total XP accumulated

    def __post_init__(self):
        self.hp = self.max_hp

class MobTrackerApp(App):
    """A command-driven mob tracker TUI."""

    def __init__(self):
        super().__init__()
        self.mobs = [
            Mob("Goblin", 7),
            Mob("Orc", 15),
            Mob("Bugbear", 27),
        ]
        self.pcs = [
            PC("Aldric", 25),
            PC("Mira", 18),
            PC("Thorin", 30),
        ]
        self.commands = {
            "add": self._command_add,
            "damage": self._command_damage,
            "check": self._command_check,
            "unstun": self._command_unstun,
            "set": self._command_set,
            "combat": self._command_combat,
            "reset": self._command_reset,
            "remove": self._command_remove,
            "clear": self._command_clear,
            "xp": self._command_xp,
            "help": self._command_help,
            "exit": self.exit,
        }
        self.command_history = []
        self.history_index = 0

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        # Main content area with PC list on left and mob list on right
        with Horizontal():
            # Left panel for PC list
            with Vertical(id="pc-panel", classes="panel"):
                yield Static(id="pc-list", classes="pc-list-panel")

            # Right panel for mob list
            with Vertical(id="mob-panel", classes="panel"):
                yield Static(id="mob-list", classes="mob-list-panel")

        # Bottom panel for log output
        with Vertical(id="bottom-panel", classes="panel"):
            yield RichLog(id="command-output", wrap=True, classes="log-panel")

        # Bottom input for commands
        yield Input(placeholder="Enter a command (type 'help' for options)", id="command-input")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is first mounted."""
        self.key_bindings()
        self.query_one("#command-input", Input).focus()

    def _refresh_display(self) -> None:
        """Refreshes both the PC and mob list panels."""
        # Update PC list panel
        pc_list = self.query_one("#pc-list", Static)

        pc_lines = []
        for i, pc in enumerate(self.pcs):
            status_icon = "[✓]" if pc.status == "Alive" else "[X]"
            stun_indicator = " ⚡" if pc.stunned else ""

            # Add morale status indicator
            morale_indicator = ""
            if pc.morale_status == "Panicked":
                morale_indicator = " 😱"
            elif pc.morale_status == "Routed":
                morale_indicator = " 🏃"

            # Show morale and min_hp only if they're not the default values for PCs
            morale_indicator_display = f" [Morale: {pc.morale}]" if pc.morale != 9 else ""
            min_hp_indicator = f" [MinHP: {pc.min_hp}]" if pc.min_hp != -10 else ""
            # Show damage stats if they're not zero
            damage_dealt_indicator = f" [Dmg+: {pc.damage_dealt}]" if pc.damage_dealt > 0 else ""
            damage_taken_indicator = f" [Dmg-: {pc.damage_taken}]" if pc.damage_taken > 0 else ""
            # Show XP if it's not zero
            xp_indicator = f" [XP: {pc.total_xp}]" if pc.total_xp > 0 else ""

            pc_lines.append(f"[{i+1}] {status_icon} {pc.name}{stun_indicator}{morale_indicator} ({pc.hp}/{pc.max_hp} HP){morale_indicator_display}{min_hp_indicator}{damage_dealt_indicator}{damage_taken_indicator}{xp_indicator}")

        pc_list.update("\n".join(pc_lines))

        # Update mob list panel
        mob_list = self.query_one("#mob-list", Static)

        mob_lines = []
        for i, mob in enumerate(self.mobs):
            # Calculate the actual index for the mob (PCs are 1 to len(pcs), so mobs start at len(pcs)+1)
            mob_actual_index = len(self.pcs) + i + 1
            status_icon = "[✓]" if mob.status == "Alive" else "[X]"
            stun_indicator = " ⚡" if mob.stunned else ""

            # Add morale status indicator
            morale_indicator = ""
            if mob.morale_status == "Panicked":
                morale_indicator = " 😱"
            elif mob.morale_status == "Routed":
                morale_indicator = " 🏃"

            # Show min_hp if it's not the default value
            min_hp_indicator = f" [MinHP: {mob.min_hp}]" if mob.min_hp != 0 else ""

            mob_lines.append(f"[{mob_actual_index}] {status_icon} {mob.name}{stun_indicator}{morale_indicator} ({mob.hp}/{mob.max_hp} HP) [Morale: {mob.morale}]{min_hp_indicator}")

        mob_list.update("\n".join(mob_lines))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Called when the user submits a command."""
        command_log = self.query_one("#command-output", RichLog)
        should_refresh = True

        command_text = event.value
        if command_text:
            self.command_history.append(command_text)
            self.history_index = len(self.command_history)

        try:
            parts = shlex.split(command_text)
            if not parts:
                return

            command = parts[0]
            args = parts[1:]
            handler = self.commands.get(command)
            if handler:
                result = handler(*args)
                if result is not None:
                    should_refresh = result
            else:
                command_log.write(f"\nUnknown command: {command}")
                should_refresh = False
        except Exception as e:
            command_log.write(f"\nError: {e}")
            should_refresh = False

        self.query_one("#command-input", Input).value = ""
        if should_refresh:
            self._refresh_display()

    async def on_key(self, event: events.Key) -> None:
        """Called when a key is pressed."""
        input_widget = self.query_one("#command-input", Input)
        if not input_widget.has_focus:
            return

        # Handle up/down arrow keys for command history
        if event.key == "up":
            self.action_history_up()
            event.prevent_default()
        elif event.key == "down":
            self.action_history_down()
            event.prevent_default()

    def _roll_dice(self, die_string: str) -> int:
        """Rolls dice based on a die string like '2d6+2' using the dice library."""
        return int(dice.roll(die_string))

    def _roll_2d6(self) -> int:
        """Rolls 2d6 for morale checks."""
        return int(dice.roll("2d6"))

    def _command_add(self, name: str, hp_str: str, *args) -> bool:
        """Adds a new mob or PC, handling duplicate names and dice notation."""
        name = name.title()
        lower_name = name.lower()

        log = self.query_one("#command-output", RichLog)

        try:
            hp = self._roll_dice(hp_str)
            log.write(f"Rolled {hp_str} for {name}: {hp} HP")
        except Exception as e:
            log.write(f"Error: Invalid HP format or dice string: {hp_str} ({e})")
            return False  # Don't refresh on error

        # Parse optional morale value
        morale = 7  # Default
        # Parse optional type (pc or mob)
        entity_type = "mob"  # Default to mob

        # Check if the first argument is the type
        if args and args[0].lower() in ["pc", "mob"]:
            entity_type = args[0].lower()
            args = args[1:]  # Remove the type from args

        # Check if the remaining first argument is the morale
        if args:
            try:
                morale = int(args[0])
                # Ensure morale is within valid range (2-12)
                morale = max(2, min(12, morale))
            except ValueError:
                log.write(f"Warning: Invalid morale value '{args[0]}', using default of 7")

        # Determine if it's a PC or mob and add accordingly
        if entity_type == "pc":
            # Check for matching PCs for duplicate handling
            matching_entities = [pc for pc in self.pcs if pc.name.lower().split(" ")[0] == lower_name]

            final_name = name
            if matching_entities:
                if len(matching_entities) == 1 and " " not in matching_entities[0].name:
                    matching_entities[0].name = f"{matching_entities[0].name} 1"

                final_name = f"{name} {len(matching_entities) + 1}"

            # PCs have default morale
            if len(args) == 0:  # Only set default if no morale was provided
                morale = 9

            self.pcs.append(PC(final_name, hp, morale=morale))
            log.write(f"Added PC: {final_name} with {hp} HP, morale {morale}")
        else:  # Default to mob
            # Check for matching mobs for duplicate handling
            matching_entities = [m for m in self.mobs if m.name.lower().split(" ")[0] == lower_name]

            final_name = name
            if matching_entities:
                if len(matching_entities) == 1 and " " not in matching_entities[0].name:
                    matching_entities[0].name = f"{matching_entities[0].name} 1"

                final_name = f"{name} {len(matching_entities) + 1}"

            self.mobs.append(Mob(final_name, hp, morale=morale))
            log.write(f"Added Mob: {final_name} with {hp} HP, morale {morale}")

        return True

    def _command_damage(self, index: str, amount: str) -> bool:
        """Applies damage to a mob or PC."""
        log = self.query_one("#command-output", RichLog)

        # Try to find the entity in PCs first, then in mobs
        try:
            entity_index = int(index) - 1
            if entity_index < len(self.pcs):
                # It's a PC
                entity = self.pcs[entity_index]
                entity_type = "PC"
            elif entity_index < len(self.pcs) + len(self.mobs):
                # It's a mob
                mob_index = entity_index - len(self.pcs)
                entity = self.mobs[mob_index]
                entity_type = "mob"
            else:
                log.write("Error: Invalid entity index.")
                return False
        except ValueError:
            log.write("Error: Invalid entity index.")
            return False

        try:
            damage = int(amount)
        except ValueError:
            log.write("Error: Invalid damage amount.")
            return False

        # Apply damage with stunning check
        self._apply_damage(entity, damage, log, entity.name)

        # Recalculate XP for all PCs
        self._recalculate_xp()

        return True

    def _command_check(self, check_type: str, index: str) -> bool:
        """Performs a morale check for a mob or PC."""
        log = self.query_one("#command-output", RichLog)

        # Try to find the entity in PCs first, then in mobs
        try:
            entity_index = int(index) - 1
            if entity_index < len(self.pcs):
                # It's a PC
                entity = self.pcs[entity_index]
            elif entity_index < len(self.pcs) + len(self.mobs):
                # It's a mob
                mob_index = entity_index - len(self.pcs)
                entity = self.mobs[mob_index]
            else:
                log.write("Error: Invalid entity index.")
                return False
        except ValueError:
            log.write("Error: Invalid entity index.")
            return False

        check_type_lower = check_type.lower()

        if check_type_lower == "braveness":
            roll = self._roll_2d6()
            if roll >= entity.morale:
                log.write(f"{entity.name} passes braveness check: {roll} vs {entity.morale} morale.")
            else:
                log.write(f"{entity.name} fails braveness check: {roll} vs {entity.morale} morale.")
                # On failure, the entity might become panicked or routed depending on interpretation
                entity.morale_status = "Panicked"
                log.write(f"{entity.name} is panicked.")
        elif check_type_lower == "boldness":
            roll = self._roll_2d6()
            if roll >= entity.morale:
                log.write(f"{entity.name} passes boldness check: {roll} vs {entity.morale} morale.")
                # Success: gain +1 permanent morale
                entity.morale = min(12, entity.morale + 1)  # Cap at 12
                log.write(f"{entity.name} morale increases to {entity.morale}.")
            else:
                log.write(f"{entity.name} fails boldness check: {roll} vs {entity.morale} morale.")
                # Failure: become panicked or routed
                entity.morale_status = "Routed"
                log.write(f"{entity.name} is routed.")
        elif check_type_lower == "panic":
            # Panic checks have a +2 bonus according to the wiki
            roll = self._roll_2d6()
            modified_roll = roll + 2
            if modified_roll >= entity.morale:
                log.write(f"{entity.name} passes panic check: {roll}+2={modified_roll} vs {entity.morale} morale.")
            else:
                log.write(f"{entity.name} fails panic check: {roll}+2={modified_roll} vs {entity.morale} morale.")
                entity.morale_status = "Panicked"
                log.write(f"{entity.name} is panicked.")
        elif check_type_lower == "rally":
            if entity.morale_status == "Normal":
                log.write(f"{entity.name} is already normal.")
                return True

            roll = self._roll_2d6()
            if roll >= entity.morale:
                log.write(f"{entity.name} rallies: {roll} vs {entity.morale} morale.")
                entity.morale_status = "Normal"
            else:
                log.write(f"{entity.name} fails rally: {roll} vs {entity.morale} morale. Status remains {entity.morale_status.lower()}.")
        else:
            log.write(f"Error: Unknown check type '{check_type}'. Supported checks: braveness, boldness, panic, rally")
            return False

        return True





    def _command_set(self, property_name: str, index: str, value: str) -> bool:
        """Sets a property of a mob or PC directly."""
        log = self.query_one("#command-output", RichLog)

        # Try to find the entity in PCs first, then in mobs
        try:
            entity_index = int(index) - 1
            if entity_index < len(self.pcs):
                # It's a PC
                entity = self.pcs[entity_index]
            elif entity_index < len(self.pcs) + len(self.mobs):
                # It's a mob
                mob_index = entity_index - len(self.pcs)
                entity = self.mobs[mob_index]
            else:
                log.write("Error: Invalid entity index.")
                return False
        except ValueError:
            log.write("Error: Invalid entity index.")
            return False

        if property_name.lower() == "morale":
            try:
                new_value = int(value)
                # Ensure morale is within valid range (2-12)
                new_value = max(2, min(12, new_value))
                old_value = entity.morale
                entity.morale = new_value
                log.write(f"{entity.name} morale changed from {old_value} to {new_value}.")
            except ValueError:
                log.write(f"Error: Invalid value '{value}' for property '{property_name}'.")
                return False
        elif property_name.lower() == "min_hp":
            try:
                new_value = int(value)
                old_value = entity.min_hp
                entity.min_hp = new_value
                log.write(f"{entity.name} minimum HP changed from {old_value} to {new_value}.")
            except ValueError:
                log.write(f"Error: Invalid value '{value}' for property '{property_name}'.")
                return False
        elif property_name.lower() == "stunned":
            if value.lower() in ["true", "yes", "1", "on"]:
                entity.stunned = True
                log.write(f"{entity.name} is stunned.")
            elif value.lower() in ["false", "no", "0", "off"]:
                entity.stunned = False
                log.write(f"{entity.name} is not stunned.")
            else:
                log.write(f"Error: Invalid value '{value}' for stunned property. Use true/false, yes/no, 1/0, or on/off.")
                return False
        elif property_name.lower() == "morale_status":
            valid_statuses = ["normal", "panicked", "routed"]
            if value.lower() in valid_statuses:
                entity.morale_status = value.lower().capitalize()
                log.write(f"{entity.name} morale status changed to {entity.morale_status}.")
            else:
                log.write(f"Error: Invalid value '{value}' for morale_status property. Use: {', '.join(valid_statuses)}")
                return False
        elif property_name.lower() == "status":
            valid_statuses = ["alive", "defeated"]
            if value.lower() in valid_statuses:
                entity.status = value.lower().capitalize()
                log.write(f"{entity.name} status changed to {entity.status}.")
            else:
                log.write(f"Error: Invalid value '{value}' for status property. Use: {', '.join(valid_statuses)}")
                return False
        else:
            log.write(f"Error: Unknown property '{property_name}'. Supported properties: morale, min_hp, stunned, morale_status, status")
            return False

        return True

    def _apply_damage(self, target, damage: int, log, target_name: str) -> None:
        """Apply damage to a target and check for stunning effects."""
        # Check if damage is 25% or more of current HP before applying damage
        # OR if target's HP is already below 0, every hit causes stun
        if (target.hp > 0 and damage >= target.hp * 0.25) or target.hp < 0:
            target.stunned = True
            log.write(f"{target_name} is stunned.")

        # Apply damage to target
        target.hp -= damage
        if target.hp <= target.min_hp:
            target.status = "Defeated"

    def _recalculate_xp(self) -> None:
        """Recalculates XP for all PCs based on current damage stats."""
        # Calculate total party damage taken by alive PCs
        total_party_damage_taken = sum(pc.damage_taken for pc in self.pcs if pc.status != "Defeated")

        for pc in self.pcs:
            if pc.status == "Defeated":
                # Dead characters receive no XP
                pc.xp_damage_taken = 0
                pc.xp_damage_dealt = 0
                pc.xp_bonus = 0
            else:
                # XP for damage taken: 20 XP per HP
                pc.xp_damage_taken = pc.damage_taken * 20

                # XP for damage dealt: 10 XP per HP
                pc.xp_damage_dealt = pc.damage_dealt * 10

                # Bonus XP: 20 XP per total HP of damage taken by friendly side
                # Distributed among alive PCs
                alive_pcs = [p for p in self.pcs if p.status != "Defeated"]
                if alive_pcs:
                    pc.xp_bonus = total_party_damage_taken * 20 // len(alive_pcs)
                else:
                    pc.xp_bonus = 0

            pc.total_xp = pc.xp_damage_taken + pc.xp_damage_dealt + pc.xp_bonus

    def _command_combat(self, attacker_index: str, target_index: str, damage_amount: str) -> bool:
        """Handles combat actions like 'combat 1 4 3' where PC 1 hits mob 4 for 3 damage."""
        log = self.query_one("#command-output", RichLog)

        try:
            attacker_idx = int(attacker_index) - 1
            target_idx = int(target_index) - 1
            damage = int(damage_amount)
        except ValueError:
            log.write("Error: Invalid entity indices or damage amount.")
            return False

        # Get attacker
        if attacker_idx < len(self.pcs):
            attacker = self.pcs[attacker_idx]
            attacker_type = "PC"
        elif attacker_idx < len(self.pcs) + len(self.mobs):
            attacker = self.mobs[attacker_idx - len(self.pcs)]
            attacker_type = "Mob"
        else:
            log.write("Error: Invalid attacker index.")
            return False

        # Get target
        if target_idx < len(self.pcs):
            target = self.pcs[target_idx]
            target_type = "PC"
        elif target_idx < len(self.pcs) + len(self.mobs):
            target = self.mobs[target_idx - len(self.pcs)]
            target_type = "Mob"
        else:
            log.write("Error: Invalid target index.")
            return False

        # Apply damage with stunning check
        self._apply_damage(target, damage, log, target.name)

        # Update damage tracking for PCs
        if attacker_type == "PC":
            attacker.damage_dealt += damage
        if target_type == "PC":
            target.damage_taken += damage

        log.write(f"{attacker.name} deals {damage} damage to {target.name}.")

        # Recalculate XP for all PCs
        self._recalculate_xp()

        return True

    def _command_remove(self, index: str) -> bool:
        """Removes a PC or mob by index."""
        log = self.query_one("#command-output", RichLog)

        try:
            entity_index = int(index) - 1
        except ValueError:
            log.write("Error: Invalid entity index.")
            return False

        if entity_index < len(self.pcs):
            # Removing a PC
            removed_pc = self.pcs.pop(entity_index)
            log.write(f"Removed PC: {removed_pc.name}")
        elif entity_index < len(self.pcs) + len(self.mobs):
            # Removing a mob
            mob_index = entity_index - len(self.pcs)
            removed_mob = self.mobs.pop(mob_index)
            log.write(f"Removed Mob: {removed_mob.name}")
        else:
            log.write("Error: Invalid entity index.")
            return False

        return True

    def _command_reset(self) -> bool:
        """Resets the damage tracking for all PCs to start a new combat."""
        log = self.query_one("#command-output", RichLog)

        # Reset damage stats for all PCs
        for pc in self.pcs:
            pc.damage_dealt = 0
            pc.damage_taken = 0

        log.write("PC damage statistics reset for new combat.")

        # Recalculate XP for all PCs
        self._recalculate_xp()

        return True

    def _command_xp(self, action: str = "") -> bool:
        """Calculates and displays XP for PCs based on combat actions."""
        log = self.query_one("#command-output", RichLog)

        action_lower = action.lower() if action else ""

        if action_lower == "calculate" or action_lower == "":
            # Recalculate XP for all PCs
            self._recalculate_xp()

            log.write("XP calculated for all PCs based on combat actions.")
            self._show_xp_breakdown()
        elif action_lower == "show":
            self._show_xp_breakdown()
        else:
            log.write("Error: Invalid action. Use 'calculate' (default), 'show', or leave empty.")
            return False

        return True

    def _show_xp_breakdown(self) -> None:
        """Shows XP breakdown for all PCs."""
        log = self.query_one("#command-output", RichLog)

        if not self.pcs:
            log.write("No PCs to show XP for.")
            return

        log.write("\nXP Breakdown:")
        for i, pc in enumerate(self.pcs):
            status = "(DEFEATED)" if pc.status == "Defeated" else ""
            log.write(f"  {i+1}. {pc.name} {status}")
            log.write(f"     Damage Taken XP: {pc.xp_damage_taken} ({pc.damage_taken} HP × 20)")
            log.write(f"     Damage Dealt XP: {pc.xp_damage_dealt} ({pc.damage_dealt} HP × 10)")
            log.write(f"     Bonus XP: {pc.xp_bonus}")
            log.write(f"     Total XP: {pc.total_xp}")

    def _command_clear(self, target: str = "") -> bool:
        """Clears PCs, mobs, or both lists."""
        log = self.query_one("#command-output", RichLog)

        target_lower = target.lower() if target else ""

        if target_lower == "pcs":
            count = len(self.pcs)
            self.pcs.clear()
            log.write(f"Cleared {count} PCs.")
        elif target_lower == "mobs":
            count = len(self.mobs)
            self.mobs.clear()
            log.write(f"Cleared {count} Mobs.")
        elif target_lower == "all":
            pc_count = len(self.pcs)
            mob_count = len(self.mobs)
            self.pcs.clear()
            self.mobs.clear()
            log.write(f"Cleared {pc_count} PCs and {mob_count} Mobs.")
        else:
            log.write("Error: Invalid target. Use 'pcs', 'mobs', or 'all'.")
            return False

        return True

    def _command_unstun(self, index: str) -> bool:
        """Removes the stunned status from a mob or PC."""
        log = self.query_one("#command-output", RichLog)

        # Try to find the entity in PCs first, then in mobs
        try:
            entity_index = int(index) - 1
            if entity_index < len(self.pcs):
                # It's a PC
                entity = self.pcs[entity_index]
            elif entity_index < len(self.pcs) + len(self.mobs):
                # It's a mob
                mob_index = entity_index - len(self.pcs)
                entity = self.mobs[mob_index]
            else:
                log.write("Error: Invalid entity index.")
                return False
        except ValueError:
            log.write("Error: Invalid entity index.")
            return False

        if entity.stunned:
            entity.stunned = False
            log.write(f"{entity.name} is no longer stunned.")
        else:
            log.write(f"{entity.name} is not stunned.")
        return True

    def _command_help(self) -> bool:
        """Displays help information."""
        log = self.query_one("#command-output", RichLog)
        log.write("\nAvailable commands:\n"
                  "- add <name> <hp or dice notation> [type] [morale] (type can be 'pc' or 'mob', defaults to 'mob')\n"
                  "- combat <attacker_index> <target_index> <damage> (e.g., combat 1 4 3 for PC 1 hitting mob 4 for 3 damage)\n"
                  "- damage <index> <amount> (index 1-N for PCs, N+1-M for mobs)\n"
                  "- remove <index> (remove entity by index)\n"
                  "- clear [pcs|mobs|all] (clear all entities of specified type)\n"
                  "- reset (reset all PC damage statistics for a new combat)\n"
                  "- xp [calculate|show] (calculate XP based on damage or show XP breakdown)\n"
                  "- check <type> <index> (perform morale checks: braveness, boldness, panic, rally, e.g., check braveness 1)\n"
                  "- set <property> <index> <value> (set entity property directly, e.g., set morale 1 5, set stunned 1 true)\n"
                  "- unstun <index>\n"
                  "- help\n"
                  "- exit")
        return False

    def exit(self) -> None:
        """Exit the application."""
        super().exit()

    def on_ready(self) -> None:
        """Called when the app is ready to start."""
        self.title = "Higher Path Combat Tracker"
        self._refresh_display()

    def key_bindings(self) -> None:
        """Define key bindings for the app."""
        self.bind("ctrl+h", "show_help", description="Show help")
        self.bind("ctrl+q", "quit_app", description="Quit application")
        self.bind("up", "history_up", description="Previous command")
        self.bind("down", "history_down", description="Next command")

    def action_show_help(self) -> None:
        """Show help information."""
        log = self.query_one("#command-output", RichLog)
        log.write("\nAvailable commands:\n"
                  "- add <name> <hp or dice notation> [type] [morale] (type can be 'pc' or 'mob', defaults to 'mob')\n"
                  "- combat <attacker_index> <target_index> <damage> (e.g., combat 1 4 3 for PC 1 hitting mob 4 for 3 damage)\n"
                  "- damage <index> <amount> (index 1-N for PCs, N+1-M for mobs)\n"
                  "- remove <index> (remove entity by index)\n"
                  "- clear [pcs|mobs|all] (clear all entities of specified type)\n"
                  "- reset (reset all PC damage statistics for a new combat)\n"
                  "- xp [calculate|show] (calculate XP based on damage or show XP breakdown)\n"
                  "- check <type> <index> (perform morale checks: braveness, boldness, panic, rally, e.g., check braveness 1)\n"
                  "- set <property> <index> <value> (set entity property directly, e.g., set morale 1 5, set stunned 1 true)\n"
                  "- unstun <index>\n"
                  "- help\n"
                  "- exit\n\n"
                  "Key bindings:\n"
                  "- Ctrl+H: Show help\n"
                  "- Ctrl+Q: Quit application\n"
                  "- Up/Down: Command history")
        self._refresh_display()

    def action_quit_app(self) -> None:
        """Quit the application."""
        self.exit()

    def action_history_up(self) -> None:
        """Go up in command history."""
        input_widget = self.query_one("#command-input", Input)
        if self.command_history:
            self.history_index = max(0, self.history_index - 1)
            input_widget.value = self.command_history[self.history_index]

    def action_history_down(self) -> None:
        """Go down in command history."""
        input_widget = self.query_one("#command-input", Input)
        if self.command_history:
            self.history_index = min(len(self.command_history), self.history_index + 1)
            if self.history_index == len(self.command_history):
                input_widget.value = ""
            else:
                input_widget.value = self.command_history[self.history_index]

CSS = """
Screen {
    background: $surface;
}

Horizontal {
    height: 1fr;
}

#pc-panel {
    width: 1fr;
    height: 1fr;
    border: none;
    background: $panel;
    padding: 0;
    margin: 0;
}

#mob-panel {
    width: 1fr;
    height: 1fr;
    border: none;
    background: $panel;
    padding: 0;
    margin: 0;
}

#bottom-panel {
    height: 1fr;
    border: none;
    background: $panel;
    padding: 0;
    margin: 0;
}

.pc-list-panel {
    height: 1fr;
    width: 1fr;
    border: none;
    background: $surface;
    padding: 1;
    content-align: left top;
}

.mob-list-panel {
    height: 1fr;
    width: 1fr;
    border: none;
    background: $surface;
    padding: 1;
    content-align: left top;
}

.log-panel {
    height: 1fr;
    width: 1fr;
    border: none;
    background: $surface;
    padding: 1;
    content-align: left top;
}


#command-input {
    height: 1;
    margin: 1 0 0 0;
    border: none;
    background: $surface;
    color: $text;
    padding: 0 1;  /* Consistent padding with other panels */
    border-top: solid $primary;
    text-style: bold;
}

Header {
    background: $primary;
    color: $text;
    text-style: bold;
}

Footer {
    display: none;
}

Static {
    border: none;
    background: $surface;
    padding: 1;
}

RichLog {
    border: none;
    background: $surface;
    content-align: left top;
}
"""

# Apply the CSS to the app
MobTrackerApp.CSS = CSS

if __name__ == "__main__":
    app = MobTrackerApp()
    app.run()
