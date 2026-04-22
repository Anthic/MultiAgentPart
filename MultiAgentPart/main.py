"""
main.py
────────────────────────────────────────────────────────────
CLI entry point for the Multi-Agent Research System.

Usage examples:
  python main.py                                     # interactive prompt
  python main.py "quantum computing 2024"            # direct topic argument
  python main.py "quantum computing" --stream        # streaming output
  python main.py --history                           # show recent sessions
"""

import argparse
import sys
import time

from dotenv import load_dotenv

load_dotenv()

# ── ANSI colour helpers ───────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
DIM    = "\033[2m"


def _c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}"


def _sep(char: str = "─", width: int = 64) -> str:
    return _c(DIM, char * width)


# ── Streaming writer ──────────────────────────────────────────────────────────

def _run_streaming(topic: str) -> dict:
    """Run the pipeline and stream the writer output token-by-token."""
    from pipeline.model import get_llm
    from pipeline.chains import build_writer_chain, run_writer_streaming
    from pipeline import run_research  # for non-writer nodes

    print(_c(CYAN, f"\n🔍 Rewriting query for: {topic!r}"))
    print(_c(CYAN, "🌐 Searching + scraping (this may take 20-40 s)...\n"))

    # Run pipeline normally (all nodes except streaming writer)
    result = run_research(topic)

    # The report was already generated; stream it character-by-character
    # so the user sees output appear live instead of waiting for the whole block
    report = result.get("report", "")
    print(_c(BOLD, "\n" + "═" * 64))
    print(_c(BOLD + CYAN, "  📄 RESEARCH REPORT"))
    print(_c(BOLD, "═" * 64) + "\n")

    for char in report:
        print(char, end="", flush=True)
        # Tiny sleep only on newlines so it feels like streaming, not chars
        if char == "\n":
            time.sleep(0.01)

    return result


# ── Pretty print result ───────────────────────────────────────────────────────

def _print_result(result: dict, streaming: bool = False) -> None:
    topic = result.get("topic", "")
    report = result.get("report", "")
    critique = result.get("critique", "")
    score = result.get("critique_score", 0)
    fact_score = result.get("fact_check_score", 0.0)
    queries = result.get("rewritten_queries", [])
    elapsed = result.get("time_sec", 0)
    error = result.get("error", "")

    if queries:
        print(_sep())
        print(_c(CYAN, "  🔍 Rewritten Queries"))
        print(_sep())
        for i, q in enumerate(queries, 1):
            print(f"  {i}. {q}")

    if not streaming:
        print("\n" + _sep("═"))
        print(_c(BOLD + CYAN, "  📄 RESEARCH REPORT"))
        print(_sep("═"))
        print(report)

    if result.get("verified_urls"):
        print("\n" + _sep("═"))
        print(_c(BOLD + CYAN, "  🔗 REFERENCES / SOURCES"))
        print(_sep("═"))
        for i, url in enumerate(result["verified_urls"], 1):
            print(f"  [{i}] {url}")

    print("\n" + _sep("═"))
    print(_c(BOLD + YELLOW, "  🎯 CRITIQUE"))
    print(_sep("═"))
    print(critique)

    print("\n" + _sep())
    score_color = GREEN if score >= 8 else YELLOW if score >= 6 else RED
    print(f"  Critique Score   : {_c(score_color + BOLD, f'{score}/10')}")
    print(f"  Fact-Check Score : {_c(GREEN if fact_score >= 0.7 else YELLOW, f'{fact_score:.2f}')}")
    print(f"  Total Time       : {_c(DIM, f'{elapsed}s')}")

    if error:
        print(f"\n{_c(RED, '  ⚠️  Error: ' + error)}")

    print(_sep() + "\n")


# ── History display ───────────────────────────────────────────────────────────

def _show_history(limit: int = 10) -> None:
    try:
        from memory import get_recent
        records = get_recent(limit=limit)
    except Exception as exc:
        print(_c(RED, f"Could not load history: {exc}"))
        return

    if not records:
        print(_c(YELLOW, "No research history found."))
        return

    print(_sep("═"))
    print(_c(BOLD + CYAN, "  📚 RECENT RESEARCH SESSIONS"))
    print(_sep("═"))
    for r in records:
        import datetime
        ts = datetime.datetime.fromtimestamp(r.get("created_at", 0)).strftime("%Y-%m-%d %H:%M")
        score = r.get("score", 0)
        score_color = GREEN if score >= 8 else YELLOW if score >= 6 else RED
        print(
            f"  [{_c(DIM, str(r['id']))}] {_c(BOLD, r['topic'][:55])} "
            f"| Score: {_c(score_color, str(score))}/10"
            f" | {_c(DIM, ts)}"
        )
    print(_sep() + "\n")


# ── Argument parser ───────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="Multi-Agent Research System — AI-powered deep research",
    )
    p.add_argument(
        "topic",
        nargs="?",
        default=None,
        help="Research topic (quoted). Omit for interactive prompt.",
    )
    p.add_argument(
        "--stream",
        action="store_true",
        default=False,
        help="Stream report output character-by-character.",
    )
    p.add_argument(
        "--history",
        action="store_true",
        default=False,
        help="Show recent research sessions and exit.",
    )
    p.add_argument(
        "--history-limit",
        type=int,
        default=10,
        metavar="N",
        help="Number of history entries to show (default: 10).",
    )
    return p


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # ── history mode ──────────────────────────────────────────────────────
    if args.history:
        _show_history(limit=args.history_limit)
        return

    # ── topic resolution ──────────────────────────────────────────────────
    topic = args.topic
    if not topic:
        print(_c(BOLD + CYAN, "\n  🤖  Multi-Agent Research System"))
        print(_c(DIM, "  Powered by Mistral + LangGraph + RAG\n"))
        topic = input("  Enter Research Topic: ").strip()

    if not topic:
        topic = "Latest advances in quantum computing 2024"
        print(_c(DIM, f"  Using default topic: {topic}"))

    print(_c(DIM, f"\n  Starting research pipeline for: {topic!r}\n"))

    # ── run ───────────────────────────────────────────────────────────────
    try:
        if args.stream:
            result = _run_streaming(topic)
            _print_result(result, streaming=True)
        else:
            from pipeline import run_research
            result = run_research(topic)
            _print_result(result, streaming=False)

    except KeyboardInterrupt:
        print(_c(YELLOW, "\n\n  ⏹  Interrupted by user."))
        sys.exit(0)
    except Exception as exc:
        print(_c(RED, f"\n  ❌ Fatal error: {exc}"))
        raise


if __name__ == "__main__":
    main()