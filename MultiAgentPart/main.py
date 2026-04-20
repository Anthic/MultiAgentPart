
from pipeline import run_research

if __name__ == "__main__":
    topic = input(" Enter Research topic:  ").strip()
    if not topic:
        topic = "Latest advances in quantum computing 2024"

    result = run_research(topic)

    print("\n" + "=" * 60)
    print(" RESEARCH REPORT")
    print("=" * 60)
    print(result["report"])

    print("\n" + "=" * 60)
    print(" CRITIQUE")
    print("=" * 60)
    print(result["critique"])

    if result["error"]:
        print(f"\n  Error: {result['error']}")

    print(f"\n  মোট সময়: {result['time_sec']} সেকেন্ড")