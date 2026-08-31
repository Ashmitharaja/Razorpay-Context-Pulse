from __future__ import annotations

import asyncio
import os
import sys

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

BACKEND_URL = os.environ.get("CONTEXTPULSE_BACKEND_URL", "http://localhost:8000")
console = Console()


async def main() -> None:
    console.print(Panel.fit(
        "[bold white on #0052FF] RAZORPAY CONTEXTPULSE [/]\nAgentic Auto-Fallback & Micro-Channel Revenue Recovery",
        border_style="#00C853", box=box.DOUBLE,
    ))

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            health = (await client.get(f"{BACKEND_URL}/health")).json()
        except httpx.ConnectError:
            console.print(f"[bold #FF5252]Backend not reachable at {BACKEND_URL}.[/] "
                          f"Start it with: [italic]uvicorn src.webhook_server:app --reload[/]")
            sys.exit(1)

        status_table = Table(box=box.SIMPLE, show_header=False)
        status_table.add_row("Razorpay", "🟢 Live" if health["razorpay_configured"] else "🔴 Not configured")
        status_table.add_row("Webhook secret", "🟢 Set" if health["webhook_secret_configured"] else "🟡 Unset (unsigned demo mode)")
        status_table.add_row("OpenAI LLM agent", "🟢 Live" if health["llm_configured"] else "🟡 Fallback engine active")
        status_table.add_row("Twilio SMS", "🟢 Live" if health["twilio_configured"] else "🟡 Not configured")
        console.print(Panel(status_table, title="[bold]Integration Status[/]", border_style="#0052FF"))

        if not health["razorpay_configured"]:
            console.print("[bold #FF5252]Add RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET to .env before running.[/]")
            sys.exit(1)

        summary_rows = []
        for i, scenario in enumerate(SCENARIOS, start=1):
            console.rule(f"[bold #0052FF]Webhook {i}/{len(SCENARIOS)}[/]")
            wh_table = Table(box=box.SIMPLE, show_header=False)
            for k, v in scenario.items():
                wh_table.add_row(k, str(v))
            console.print(Panel(wh_table, title="[bold]Simulated payment.failed webhook[/]", border_style="#FF5252"))

            with console.status("[cyan]Signing webhook, running agent, calling Razorpay...[/]"):
                resp = await client.post(f"{BACKEND_URL}/simulate/payment-failed",
                                         json={**scenario, "send_notifications": False})
            data = resp.json()

            if "error" in data:
                console.print(f"[bold #FF5252]Pipeline error:[/] {data['error']}")
                continue

            console.print(Panel(
                "\n".join(f"→ {s}" for s in data.get("reasoning", [])),
                title=f"[bold #0052FF]Agent Reasoning ({data.get('decided_by')})[/]", border_style="#0052FF",
            ))

            decision_table = Table(box=box.SIMPLE, show_header=False)
            decision_table.add_row("Channel", f"[bold #00C853]{data.get('channel')}[/]")
            decision_table.add_row("Confidence", f"{data.get('confidence', 0) * 100:.1f}%")
            decision_table.add_row("Live Payment Link", data.get("payment_link", ""))
            console.print(Panel(decision_table, title="[bold]Recovery Strategy + Real Razorpay Link[/]", border_style="#00C853"))

            summary_rows.append((scenario["customer_name"], scenario["decline_reason"],
                                  data.get("channel", ""), f"₹{scenario['amount']:,.2f}"))

        console.rule("[bold #0052FF]Summary[/]")
        summary = Table(title="ContextPulse Run Ledger", box=box.ROUNDED, border_style="#0052FF")
        summary.add_column("Customer")
        summary.add_column("Decline Reason", style="#FF5252")
        summary.add_column("Recovery Channel", style="#00C853")
        summary.add_column("Amount", justify="right")
        for row in summary_rows:
            summary.add_row(*row)
        console.print(summary)

        metrics = (await client.get(f"{BACKEND_URL}/metrics")).json()
        m_table = Table(box=box.HEAVY_EDGE, border_style="#00C853", show_header=False)
        m_table.add_row("Failed Revenue Analyzed", f"₹{metrics['failed_revenue_analyzed']:,.2f}")
        m_table.add_row("Auto-Recoveries", f"{int(metrics['auto_recoveries'])} / {int(metrics['total_events'])}")
        m_table.add_row("Est. Conversion Lift", f"{metrics['conversion_lift_pct']:.1f}%")
        console.print(Panel(m_table, title="[bold white on #0052FF] Impact Metrics (from SQLite) [/]", border_style="#0052FF"))

    console.print("\n[bold #00C853]Launch the dashboard:[/] [italic]streamlit run dashboard.py[/]\n")


if __name__ == "__main__":
    asyncio.run(main())