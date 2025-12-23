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
            lines.append(f"[{i+1}] {status_icon} {mob.name} ({mob.hp}/{mob.max_hp} HP)")
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

    def _command_add(self, name: str, hp_str: str) -> bool:
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

        matching_mobs = [m for m in self.mobs if m.name.lower().split(" ")[0] == lower_name]

        final_name = name
        if matching_mobs:
            if len(matching_mobs) == 1 and " " not in matching_mobs[0].name:
                matching_mobs[0].name = f"{matching_mobs[0].name} 1"

            final_name = f"{name} {len(matching_mobs) + 1}"

        self.mobs.append(Mob(final_name, hp))
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

        mob.hp -= damage
        if mob.hp <= 0:
            mob.hp = 0
            mob.status = "Defeated"
        return True

    def _command_help(self) -> bool:
        """Displays help information."""
        log = self.query_one("#display")
        log.write("\nAvailable commands:\n"
                  "- add <name> <hp or dice notation, e.g., 2d8+2, 4d6L>\n"
                  "- damage <index> <amount>\n"
                  "- help\n"
                  "- exit")
        return False

    def exit(self) -> None:
        """Exit the application."""
        super().exit()

if __name__ == "__main__":
    app = MobTrackerApp()
    app.run()
