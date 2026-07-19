from spin_fm import __version__
from spin_fm.app import build_parser


def test_cli_collects_paths() -> None:
    args = build_parser().parse_args(["/tmp/a", "file:///tmp/b"])
    assert args.paths == ["/tmp/a", "file:///tmp/b"]
    assert __version__ == "2.6.14"
