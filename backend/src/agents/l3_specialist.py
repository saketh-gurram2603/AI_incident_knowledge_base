"""
L3 Specialist node — pure routing with zero LLM calls.

When both L1 and L2 fail to reach sufficient confidence, L3:
  1. Inserts an escalation ticket into Postgres
  2. Returns the ticket ID and a clear escalation message
  3. Sets escalation_level = "L3" and final_answer to the ticket reference

SQLAlchemy ORM model EscalationTicketDB is defined here so main.py can import
it before calling create_tables(), ensuring the table is created at startup.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.agents.state import IncidentState
from src.handlers.logger import get_logger, log_error, log_info, log_warning
from src.integrations.database import Base, get_session

logger = get_logger("agents.l3_specialist")


# ── ORM model ─────────────────────────────────────────────────────────────────


class EscalationTicketDB(Base):
    """
    Postgres table for L3 escalation tickets.

    Imported by main.py before create_tables() so the table is created at
    startup via Base.metadata.create_all().
    """

    __tablename__ = "escalation_tickets"

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(String(32), nullable=True)
    urgency: Mapped[str] = mapped_column(String(32), nullable=True)
    priority: Mapped[str] = mapped_column(String(8), nullable=True)
    l1_summary: Mapped[str] = mapped_column(Text, nullable=True)
    l2_analysis: Mapped[str] = mapped_column(Text, nullable=True)
    escalation_reason: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="OPEN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ── Node factory ──────────────────────────────────────────────────────────────


def make_l3_node() -> Callable[[IncidentState], dict]:
    """
    Factory: returns an async L3 specialist node.
    No external config needed — pure Postgres write + return.
    """

    async def l3_node(state: IncidentState) -> dict:
        query = state.get("query", "")
        impact = state.get("impact", "")
        urgency = state.get("urgency", "")
        priority = state.get("priority")
        l1_summary = state.get("l1_summary", "")
        l2_synthesis = state.get("l2_synthesis", "")
        escalation_reason = state.get("escalation_reason", "Escalated after L1 + L2 failed.")

        log_info("L3 node | creating escalation ticket | query='%s'", query[:80])

        ticket_id = _generate_ticket_id()

        # ── Write escalation ticket to Postgres ────────────────────────────────
        ticket_written = await _write_ticket(
            ticket_id=ticket_id,
            description=query,
            impact=impact,
            urgency=urgency,
            priority=priority,
            l1_summary=l1_summary,
            l2_analysis=l2_synthesis,
            escalation_reason=escalation_reason,
        )

        if ticket_written:
            log_info("L3 escalation ticket created | ticket_id=%s", ticket_id)
        else:
            log_warning("L3 ticket write failed — returning in-memory ticket_id=%s", ticket_id)

        final_answer = (
            f"This incident has been escalated to the specialist team.\n"
            f"Ticket ID: {ticket_id}\n"
            f"Status: OPEN — assigned to IT-OPS escalation queue.\n\n"
            f"Escalation reason: {escalation_reason}"
        )

        return {
            "escalation_ticket_id": ticket_id,
            "final_answer": final_answer,
            "escalation_level": "L3",
            "model_used": "none",
            "fallback_used": False,
        }

    return l3_node


# ── Private helpers ───────────────────────────────────────────────────────────


def _generate_ticket_id() -> str:
    """Generate a unique ticket ID in the format TKT-<8 uppercase hex chars>."""
    return f"TKT-{uuid.uuid4().hex[:8].upper()}"


async def _write_ticket(
    ticket_id: str,
    description: str,
    impact: str,
    urgency: str,
    priority: str | None,
    l1_summary: str,
    l2_analysis: str,
    escalation_reason: str,
) -> bool:
    """
    Insert the escalation ticket into Postgres.
    Returns True on success, False on failure (caller logs appropriately).
    """
    try:
        async with get_session() as session:
            ticket = EscalationTicketDB(
                ticket_id=ticket_id,
                description=description[:2000],
                impact=impact or None,
                urgency=urgency or None,
                priority=priority or None,
                l1_summary=l1_summary[:2000] if l1_summary else None,
                l2_analysis=l2_analysis[:2000] if l2_analysis else None,
                escalation_reason=escalation_reason[:1000],
                status="OPEN",
            )
            session.add(ticket)
        return True
    except Exception as exc:
        log_error("L3 ticket DB write failed | ticket_id=%s error=%s", ticket_id, exc)
        return False


async def list_escalation_tickets(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """
    Fetch escalation tickets from Postgres.
    Optionally filter by status ("OPEN", "IN_PROGRESS", "RESOLVED").
    """
    from sqlalchemy import select

    try:
        async with get_session() as session:
            stmt = select(EscalationTicketDB).order_by(
                EscalationTicketDB.created_at.desc()
            )
            if status:
                stmt = stmt.where(EscalationTicketDB.status == status)
            stmt = stmt.offset(offset).limit(limit)
            result = await session.execute(stmt)
            rows = result.scalars().all()
            return [_ticket_to_dict(row) for row in rows]
    except Exception as exc:
        log_error("list_escalation_tickets failed | error=%s", exc)
        return []


def _ticket_to_dict(ticket: EscalationTicketDB) -> dict:
    """Convert ORM row to plain dict for API serialisation."""
    return {
        "ticket_id": ticket.ticket_id,
        "description": ticket.description,
        "impact": ticket.impact,
        "urgency": ticket.urgency,
        "l1_summary": ticket.l1_summary,
        "l2_analysis": ticket.l2_analysis,
        "escalation_reason": ticket.escalation_reason,
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else "",
    }
