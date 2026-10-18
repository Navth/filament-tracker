"""Command line: ft-agent login | logout | chat | ask."""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path

from .config import config_dir

DEMO_FIXTURE = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "demo.json"


def _service(demo: bool):
    from .repository import FilamentService, FixtureBackend

    if demo:
        return FilamentService(FixtureBackend.from_file(DEMO_FIXTURE))
    from .auth import supabase_backend

    return FilamentService(supabase_backend())


def _describe(action: dict) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in action["input"].items())
    return f"{action['tool']}({args})"


def _print_answer(result, verbose: bool) -> None:
    a = result.answer
    print(f"\n{a.answer}\n")
    if verbose:
        print(f"  verdict={a.verdict} spools={a.spool_ids} confidence={a.confidence}")
        for t in result.trace:
            print("  tool:", json.dumps(t, default=str)[:200])
        print("  usage:", result.usage)


async def _turn(agent, thread: str, question: str, auto_yes: bool, verbose: bool) -> None:
    result = await agent.ask(thread, question)
    while result.status == "needs_approval":
        decisions = {}
        for action in result.approval["actions"]:
            if auto_yes:
                ok = True
            else:
                ok = input(f"Allow {_describe(action)}? [y/N] ").strip().lower() in ("y", "yes")
            decisions[action["id"]] = ok
        result = await agent.resume(thread, decisions)
    _print_answer(result, verbose)


async def _run(args) -> None:
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    from .agent import FilamentAgent

    service = _service(args.demo)
    db = config_dir() / ("threads-demo.sqlite" if args.demo else "threads.sqlite")
    async with AsyncSqliteSaver.from_conn_string(str(db)) as saver:
        async with FilamentAgent(service, checkpointer=saver) as agent:
            if args.command == "ask":
                await _turn(agent, args.thread, " ".join(args.question), args.yes, args.verbose)
                return
            print("Filament Tracker agent. Ask about your spools; 'exit' to quit.")
            while True:
                try:
                    q = input("you> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return
                if q.lower() in ("exit", "quit"):
                    return
                if q:
                    await _turn(agent, args.thread, q, args.yes, args.verbose)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="ft-agent", description="Chat with your Filament Tracker data.")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("login", help="sign in with your Filament Tracker account")
    sub.add_parser("logout", help="forget the saved session")
    for name in ("chat", "ask"):
        sp = sub.add_parser(name, help="interactive chat" if name == "chat" else "ask one question")
        sp.add_argument("--demo", action="store_true", help="use the built-in demo data instead of your account")
        sp.add_argument("--thread", default="default", help="conversation id (kept between runs)")
        sp.add_argument("--yes", action="store_true", help="approve changes without asking")
        sp.add_argument("-v", "--verbose", action="store_true", help="show tool calls and token usage")
        if name == "ask":
            sp.add_argument("question", nargs="+")
    args = p.parse_args(argv)

    if args.command == "login":
        from .auth import login

        email = input("Email: ").strip()
        password = getpass.getpass("Password: ")
        try:
            print(f"Signed in as {login(email, password)}")
        except RuntimeError as e:
            sys.exit(str(e))
        return
    if args.command == "logout":
        from .auth import logout

        logout()
        print("Signed out.")
        return
    try:
        asyncio.run(_run(args))
    except RuntimeError as e:
        sys.exit(str(e))
    except TypeError as e:
        if "authentication" not in str(e):
            raise
        sys.exit("No Anthropic API credentials. Set ANTHROPIC_API_KEY (see agent/.env.example).")
    except ValueError as e:
        if "API key" not in str(e) and "api_key" not in str(e):
            raise
        sys.exit("No Gemini API key. Set GEMINI_API_KEY in agent/.env (see agent/.env.example).")


if __name__ == "__main__":
    main()
