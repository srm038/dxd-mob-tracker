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
            "check": self._command_check,
            "rally": self._command_rally,
            "unstun": self._command_unstun,
            "set": self._command_set,
            "help": self._command_help,
            "exit": self.exit,
        }
        self.command_history = []
        self.history_index = 0

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        # Main content area with mob list on left and log on right
        with Horizontal():
            # Left panel for mob list
            with Vertical(id="left-panel", classes="panel"):
                yield Static(id="mob-list", classes="mob-list-panel")

            # Right panel for log output
            with Vertical(id="right-panel", classes="panel"):
                yield RichLog(id="command-output", wrap=True, classes="log-panel")

        # Bottom input for commands
        yield Input(placeholder="Enter a command (type 'help' for options)", id="command-input")
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is first mounted."""
        self.key_bindings()
        self.query_one("#command-input", Input).focus()

    def _refresh_mob_list(self) -> None:
        """Refreshes the mob list panel."""
        mob_list = self.query_one("#mob-list", Static)

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

            # Show min_hp if it's not the default value
            min_hp_indicator = f" [MinHP: {mob.min_hp}]" if mob.min_hp != 0 else ""

            lines.append(f"[{i+1}] {status_icon} {mob.name}{stun_indicator}{morale_indicator} ({mob.hp}/{mob.max_hp} HP) [Morale: {mob.morale}]{min_hp_indicator}")

        mob_list.update("\n".join(lines))

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
            self._refresh_mob_list()

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
        """Adds a new mob, handling duplicate names and dice notation."""
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
        log = self.query_one("#command-output", RichLog)

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
        if mob.hp <= mob.min_hp:
            mob.status = "Defeated"
        return True

    def _command_check(self, check_type: str, index: str) -> bool:
        """Performs a morale check for a mob."""
        log = self.query_one("#command-output", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index.")
            return False  # Don't refresh on error

        check_type_lower = check_type.lower()

        if check_type_lower == "braveness":
            roll = self._roll_2d6()
            if roll >= mob.morale:
                log.write(f"{mob.name} passes braveness check (rolled {roll} vs {mob.morale} morale) - ready for melee!")
            else:
                log.write(f"{mob.name} fails braveness check (rolled {roll} vs {mob.morale} morale) - won't engage in melee!")
                # On failure, the mob might become panicked or routed depending on interpretation
                mob.morale_status = "Panicked"
                log.write(f"{mob.name} is now panicked!")
        elif check_type_lower == "boldness":
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
        elif check_type_lower == "panic":
            # Panic checks have a +2 bonus according to the wiki
            roll = self._roll_2d6()
            modified_roll = roll + 2
            if modified_roll >= mob.morale:
                log.write(f"{mob.name} passes panic check (rolled {roll}+2={modified_roll} vs {mob.morale} morale) - holds position!")
            else:
                log.write(f"{mob.name} fails panic check (rolled {roll}+2={modified_roll} vs {mob.morale} morale) - panics!")
                mob.morale_status = "Panicked"
                log.write(f"{mob.name} is now panicked!")
        else:
            log.write(f"Error: Unknown check type '{check_type}'. Supported checks: braveness, boldness, panic")
            return False

        return True




    def _command_rally(self, index: str) -> bool:
        """Allows a panicked or routed mob to attempt to rally."""
        log = self.query_one("#command-output", RichLog)

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

    def _command_set(self, property_name: str, index: str, value: str) -> bool:
        """Sets a property of a mob directly."""
        log = self.query_one("#command-output", RichLog)

        try:
            mob_index = int(index) - 1
            mob = self.mobs[mob_index]
        except (ValueError, IndexError):
            log.write("Error: Invalid mob index.")
            return False  # Don't refresh on error

        if property_name.lower() == "morale":
            try:
                new_value = int(value)
                # Ensure morale is within valid range (2-12)
                new_value = max(2, min(12, new_value))
                old_value = mob.morale
                mob.morale = new_value
                log.write(f"{mob.name}'s morale changed from {old_value} to {new_value}.")
            except ValueError:
                log.write(f"Error: Invalid value '{value}' for property '{property_name}'.")
                return False
        elif property_name.lower() == "min_hp":
            try:
                new_value = int(value)
                old_value = mob.min_hp
                mob.min_hp = new_value
                log.write(f"{mob.name}'s minimum HP changed from {old_value} to {new_value}.")
            except ValueError:
                log.write(f"Error: Invalid value '{value}' for property '{property_name}'.")
                return False
        elif property_name.lower() == "stunned":
            if value.lower() in ["true", "yes", "1", "on"]:
                mob.stunned = True
                log.write(f"{mob.name} is now stunned.")
            elif value.lower() in ["false", "no", "0", "off"]:
                mob.stunned = False
                log.write(f"{mob.name} is no longer stunned.")
            else:
                log.write(f"Error: Invalid value '{value}' for stunned property. Use true/false, yes/no, 1/0, or on/off.")
                return False
        elif property_name.lower() == "morale_status":
            valid_statuses = ["normal", "panicked", "routed"]
            if value.lower() in valid_statuses:
                mob.morale_status = value.lower().capitalize()
                log.write(f"{mob.name}'s morale status changed to {mob.morale_status}.")
            else:
                log.write(f"Error: Invalid value '{value}' for morale_status property. Use: {', '.join(valid_statuses)}")
                return False
        elif property_name.lower() == "status":
            valid_statuses = ["alive", "defeated"]
            if value.lower() in valid_statuses:
                mob.status = value.lower().capitalize()
                log.write(f"{mob.name}'s status changed to {mob.status}.")
            else:
                log.write(f"Error: Invalid value '{value}' for status property. Use: {', '.join(valid_statuses)}")
                return False
        else:
            log.write(f"Error: Unknown property '{property_name}'. Supported properties: morale, min_hp, stunned, morale_status, status")
            return False

        return True

    def _command_unstun(self, index: str) -> bool:
        """Removes the stunned status from a mob."""
        log = self.query_one("#command-output", RichLog)

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
        log = self.query_one("#command-output", RichLog)
        log.write("\nAvailable commands:\n"
                  "- add <name> <hp or dice notation> [morale]\n"
                  "- damage <index> <amount>\n"
                  "- check <type> <index> (perform morale checks: braveness, boldness, panic, e.g., check braveness 1)\n"
                  "- rally <index> (attempt to recover from panic/route)\n"
                  "- set <property> <index> <value> (set mob property directly, e.g., set morale 1 5, set stunned 1 true)\n"
                  "- unstun <index>\n"
                  "- help\n"
                  "- exit")
        return False

    def exit(self) -> None:
        """Exit the application."""
        super().exit()

    def on_ready(self) -> None:
        """Called when the app is ready to start."""
        self._refresh_mob_list()

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
                  "- add <name> <hp or dice notation> [morale]\n"
                  "- damage <index> <amount>\n"
                  "- check <type> <index> (perform morale checks: braveness, boldness, panic, e.g., check braveness 1)\n"
                  "- rally <index> (attempt to recover from panic/route)\n"
                  "- set <property> <index> <value> (set mob property directly, e.g., set morale 1 5, set stunned 1 true)\n"
                  "- unstun <index>\n"
                  "- help\n"
                  "- exit\n\n"
                  "Key bindings:\n"
                  "- Ctrl+H: Show help\n"
                  "- Ctrl+Q: Quit application\n"
                  "- Up/Down: Command history")
        self._refresh_mob_list()

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

#left-panel {
    width: 2fr;
    height: 1fr;
    border: solid $primary;
    background: $panel;
    padding: 0;
    margin: 0;
}

#right-panel {
    width: 1fr;
    height: 1fr;
    border: solid $success;
    background: $panel;
    padding: 0;
    margin: 0;
}

.mob-list-panel {
    height: 1fr;
    width: 1fr;
    border: solid $primary;
    background: $surface;
    padding: 1;
    content-align: left top;
}

.log-panel {
    height: 1fr;
    width: 1fr;
    border: solid $success;
    background: $surface;
    padding: 1;
    content-align: left top;
}

#command-input {
    height: 1;
    margin: 1 0 0 0;
    border: solid $warning;
    background: $surface;
    color: $text;
    padding: 0 1;
}

Header {
    background: $primary;
    color: $text;
    text-style: bold;
}

Footer {
    background: $primary;
    color: $text;
    text-style: bold;
}

Static {
    border: none;
    background: $surface;
}

RichLog {
    border: none;
    background: $surface;
}
"""

# Apply the CSS to the app
MobTrackerApp.CSS = CSS

if __name__ == "__main__":
    app = MobTrackerApp()
    app.run()
