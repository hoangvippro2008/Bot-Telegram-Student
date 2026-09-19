from pathlib import Path

from bot.app import run


def main() -> None:
    config_path = Path(__file__).resolve().with_name("config.json")
    run(config_path)


if __name__ == "__main__":
    main()
