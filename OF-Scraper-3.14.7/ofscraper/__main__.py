from click.exceptions import ClickException

# The command line is parsed while the app's modules are imported, and with
# standalone_mode=False click leaves usage errors to the caller. Handle them
# only here, in the real program: other code that imports ofscraper may run
# with a command line that isn't ours and relies on those errors not exiting.
try:
    import ofscraper.main.open.load as load
except ClickException as e:
    e.show()
    raise SystemExit(e.exit_code)


def main():
    load.main()


if __name__ == "__main__":
    main()
