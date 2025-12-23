import shlex
import dice
from dataclasses import dataclass, field
from textual.app import App, ComposeResult
from textual import events
from textual.widgets import Header, Footer, RichLog, Input

@dataclass
class Mob:
    name: str
    max_hp: int
    hp: int = field(init=False)
    status: str = "Alive"
    stunned: bool = False
    morale: int = 7  # Default morale rating (7 for clan fighters, etc.)
    morale_status: str = "Normal"  # Normal, Panicked, Routed

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
        self.commands = {
            "add": self._command_add,
            "damage": self._command_damage,
            "braveness": self._command_braveness,
            "boldness": self._command_boldness,
            "panic": self._command_panic,
            "rally": self._command_rally,
            "unstun": self._command_unstun,
            "help": self._command_help,
            "exit": self.exit,
        }
        self.command_history = []
        self.history_index = 0

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield RichLog(id="display", wrap=True)
        yield Input(placeholder="Enter a command (type 'help' for options)")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is first mounted."""
        self._refresh_display()
        self.query_one(Input).focus()

    def _refresh_display(self) -> None:
        """Refreshes the main display with the current mob list."""
        log = self.query_one("#display", RichLog)
        log.clear()

        lines = []
        for i, mob in enumerate(self.mobs):
            status_icon = "[✓]" if mob.status == "Alive" else "[X]"
            stun_indicator = " ⚡" if mob.stunned else ""

            # Add morale status indicator
            morale_indicator = ""
            if mob.morale_status == "Panicked":
                morale_indicator = " 😱"
            elif mob.morale_status == "Routed":
                morale_indicator = " 🏃"

            lines.append(f"[{i+1}] {status_icon} {mob.name}{stun_indicator}{morale_indicator} ({mob.hp}/{mob.max_hp} HP) [Morale: {mob.morale}]")
        log.write("\n".join(lines))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Called when the user submits a command."""
        command_log = self.query_one("#display")
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
        
        self.query_one(Input).value = ""
        if should_refresh:
            self._refresh_display()

    async def on_key(self, event: events.Key) -> None:
        """Called when a key is pressed."""
        input_widget = self.query_one(Input)
        if not input_widget.has_focus:
            return

        if event.key == "up":
            if self.command_history:
                self.history_index = max(0, self.history_index - 1)
                input_widget.value = self.command_history[self.history_index]
            event.prevent_default()
        elif event.key == "down":
            if self.command_history:
                self.history_index = min(len(self.command_history), self.history_index + 1)
                if self.history_index == len(self.command_history):
                    input_widget.value = ""
                else:
                    input_widget.value = self.command_history[self.history_index]
            event.prevent_default()

    def _roll_dice(self, die_string: str) -> int:
        """Rolls dice based on a die string like '2d6+2' using the dice library."""
        return int(dice.roll(die_string))

    def _roll_2d6(self) -> int:
        """Rolls 2d6 for morale checks."""
        return int(dice.roll("2d6"))

    def _command_add(self, name: str, hp_str: str, *args) -> bool:
        """Adds a new mob, handling duplicate names and dice notation."""
        name = name.title()
        lower_name = name.lower()

        log = self.query_one("#display", RichLog)

        try:
            hp = self._roll_dice(hp_str)
            log.write(f"Rolled {hp_str} for {name}: {hp} HP")
        except Exception as e:
            log.write(f"Error: Invalid HP format or dice string: {hp_str} ({e})")
            return False  # Don't refresh on error

        # Parse optional morale value
        morale = 7  # Default
        if args:
            try:
                morale = int(args[0])
                # Ensure morale is within valid range (2-12)
                morale = max(2, min(12, morale))
            except ValueError:
                log.write(f"Warning: Invalid morale value '{args[0]}', using default of 7")

        matching_mobs = [m for m in self.mobs if m.name.lower().split(" ")[0] == lower_name]

        final_name = name
        if matching_mobs:
            if len(matching_mobs) == 1 and " " not in matching_mobs[0].name:
                matching_mobs[0].name = f"{matching_mobs[0].name} 1"

            final_name = f"{name} {len(matching_mobs) + 1}"

        self.mobs.append(Mob(final_name, hp, morale=morale))
        return True

    def _command_damage(self, index: str, amount: str) -> bool:
        """Applies damage to a mob."""
        log = self.query_one("#display", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
            damage = int(amount)
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index or damage amount.")
            return False  # Don't refresh on error

        # Check if damage is 25% or more of current HP before applying damage
        # OR if mob's HP is already below 0, every hit causes stun
        if (mob.hp > 0 and damage >= mob.hp * 0.25) or mob.hp < 0:
            mob.stunned = True
            log.write(f"{mob.name} has been stunned!")

        mob.hp -= damage
        if mob.hp <= 0:
            mob.status = "Defeated"
        return True

    def _command_braveness(self, index: str) -> bool:
        """Performs a braveness check for a mob to enter melee combat."""
        log = self.query_one("#display", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index.")
            return False  # Don't refresh on error

        roll = self._roll_2d6()
        if roll >= mob.morale:
            log.write(f"{mob.name} passes braveness check (rolled {roll} vs {mob.morale} morale) - ready for melee!")
        else:
            log.write(f"{mob.name} fails braveness check (rolled {roll} vs {mob.morale} morale) - won't engage in melee!")
            # On failure, the mob might become panicked or routed depending on interpretation
            mob.morale_status = "Panicked"
            log.write(f"{mob.name} is now panicked!")

    def _command_boldness(self, index: str) -> bool:
        """Performs a boldness check when a mob takes damage."""
        log = self.query_one("#display", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index.")
            return False  # Don't refresh on error

        roll = self._roll_2d6()
        if roll >= mob.morale:
            log.write(f"{mob.name} passes boldness check (rolled {roll} vs {mob.morale} morale) - continues fighting!")
            # Success: gain +1 permanent morale
            mob.morale = min(12, mob.morale + 1)  # Cap at 12
            log.write(f"{mob.name}'s morale increases to {mob.morale}!")
        else:
            log.write(f"{mob.name} fails boldness check (rolled {roll} vs {mob.morale} morale) - falls back/routs!")
            # Failure: become panicked or routed
            mob.morale_status = "Routed"
            log.write(f"{mob.name} is now routed!")

        return True

    def _command_panic(self, index: str) -> bool:
        """Forces a panic check for a mob when allies are killed nearby."""
        log = self.query_one("#display", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index.")
            return False  # Don't refresh on error

        # Panic checks have a +2 bonus according to the wiki
        roll = self._roll_2d6()
        modified_roll = roll + 2
        if modified_roll >= mob.morale:
            log.write(f"{mob.name} passes panic check (rolled {roll}+2={modified_roll} vs {mob.morale} morale) - holds position!")
        else:
            log.write(f"{mob.name} fails panic check (rolled {roll}+2={modified_roll} vs {mob.morale} morale) - panics!")
            mob.morale_status = "Panicked"
            log.write(f"{mob.name} is now panicked!")

        return True

    def _command_rally(self, index: str) -> bool:
        """Allows a panicked or routed mob to attempt to rally."""
        log = self.query_one("#display", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index.")
            return False  # Don't refresh on error

        if mob.morale_status == "Normal":
            log.write(f"{mob.name} is already normal and doesn't need to rally.")
            return True

        roll = self._roll_2d6()
        if roll >= mob.morale:
            log.write(f"{mob.name} successfully rallies (rolled {roll} vs {mob.morale} morale) - returns to normal!")
            mob.morale_status = "Normal"
        else:
            log.write(f"{mob.name} fails to rally (rolled {roll} vs {mob.morale} morale) - remains {mob.morale_status.lower()}.")

        return True

    def _command_unstun(self, index: str) -> bool:
        """Removes the stunned status from a mob."""
        log = self.query_one("#display", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index.")
            return False  # Don't refresh on error

        if mob.stunned:
            mob.stunned = False
            log.write(f"{mob.name} has been unstunned!")
        else:
            log.write(f"{mob.name} is not stunned.")
        return True

    def _command_help(self) -> bool:
        """Displays help information."""
        log = self.query_one("#display")
        log.write("\nAvailable commands:\n"
                  "- add <name> <hp or dice notation> [morale]\n"
                  "- damage <index> <amount>\n"
                  "- braveness <index> (check to enter melee)\n"
                  "- boldness <index> (check when taking damage)\n"
                  "- panic <index> (check when allies are killed)\n"
                  "- rally <index> (attempt to recover from panic/route)\n"
                  "- unstun <index>\n"
                  "- help\n"
                  "- exit")
        return False

    def exit(self) -> None:
        """Exit the application."""
        super().exit()

if __name__ == "__main__":
    app = MobTrackerApp()
    app.run()
