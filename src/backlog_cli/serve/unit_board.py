"""The units of one item as blocks with a route of six stations."""

from dataclasses import dataclass

from backlog_cli.domain.action import Action
from backlog_cli.domain.item import Item
from backlog_cli.domain.part import Correction, PrRef
from backlog_cli.domain.unit import PrUnit, ResearchUnit, Unit
from backlog_cli.domain.vocabulary import ActionStatus, UnitStatus
from backlog_cli.serve.anchor import Anchor
from backlog_cli.serve.path_links import PathLinks
from backlog_cli.serve.reasons import ReasonText
from backlog_cli.serve.text import HtmlText, LocalDate
from backlog_cli.serve.view import WorkspaceView


@dataclass
class Station:
    state: str  # passed, reached, future or na (skipped)
    when_html: str = ""
    is_passed: bool = False  # a skipped station the unit has gone beyond


class UnitRoute:
    """Which stations a unit has passed and where it stands."""

    PR_STATIONS = ("Created", "In progress", "Merged", "Released", "Checks", "Done")
    CHECKS = 4
    DONE = 5
    CSS = {
        UnitStatus.TODO: "r-todo",
        UnitStatus.WIP: "r-wip",
        UnitStatus.MERGED: "r-merged",
        UnitStatus.POST_RELEASE: "r-released",
        UnitStatus.DONE: "r-done",
        UnitStatus.CANCELLED: "r-gone",
        UnitStatus.SUPERSEDED: "r-gone",
    }

    @classmethod
    def build_css(cls, unit: Unit) -> str:
        if isinstance(unit, PrUnit) and any(a.is_failed for a in unit.pending_actions):
            return "r-failed"
        return cls.CSS[unit.status]

    @classmethod
    def build_stations(cls, unit: Unit) -> list[Station]:
        reached = cls._find_reached(unit)
        stations = []
        for index in range(len(cls.PR_STATIONS)):
            if isinstance(unit, ResearchUnit) and index in (2, 3, 4):
                stations.append(Station("na", is_passed=index < reached))
                continue
            state = (
                "passed"
                if index < reached
                else "reached"
                if index == reached
                else "future"
            )
            stations.append(Station(state, cls._describe_when(unit, index, state)))
        return stations

    @classmethod
    def _find_reached(cls, unit: Unit) -> int:
        if unit.status in (UnitStatus.CANCELLED, UnitStatus.SUPERSEDED):
            return 1 if unit.has_started else 0
        positions = {
            UnitStatus.TODO: 0,
            UnitStatus.WIP: 1,
            UnitStatus.MERGED: 2,
            UnitStatus.POST_RELEASE: cls.CHECKS,
            UnitStatus.DONE: cls.DONE,
        }
        return positions[unit.status]

    @classmethod
    def _describe_when(cls, unit: Unit, index: int, state: str) -> str:
        if state == "reached" and unit.status in (
            UnitStatus.CANCELLED,
            UnitStatus.SUPERSEDED,
        ):
            return cls._describe_end(unit)
        if isinstance(unit, PrUnit) and index == cls.CHECKS:
            return cls._describe_checks(unit, state)
        if state == "future":
            return ""
        if index == cls.DONE and unit.completion is not None:
            return LocalDate.html(unit.completion.completed_at, False)
        if isinstance(unit, PrUnit) and index == 2 and unit.merge is not None:
            merge = unit.merge
            return LocalDate.html(merge.merged_at or merge.evidence.recorded_at, False)
        if isinstance(unit, PrUnit) and index == 3 and unit.release is not None:
            return LocalDate.html(unit.release.released_at, False)
        return ""

    @staticmethod
    def _describe_end(unit: Unit) -> str:
        completion = unit.completion
        word = "cancelled"
        if completion.superseded_by:
            word = f"superseded by {HtmlText.esc(completion.superseded_by)}"
        elif completion.outcome == "superseded":
            word = "superseded"
        return f'<span title="{HtmlText.esc(completion.reason or "")}">{word}</span>'

    @staticmethod
    def _describe_checks(unit: PrUnit, state: str) -> str:
        live = unit.live_actions
        if not live:
            return "none" if unit.merge is not None else ""
        if state == "future":
            return ""
        if any(action.is_failed for action in unit.pending_actions):
            return "failed"
        if unit.pending_actions:
            return "waiting"
        confirmed = [a.confirmation for a in live if a.confirmation is not None]
        latest = max((c.observed_at or c.recorded_at for c in confirmed), default=None)
        return LocalDate.html(latest, False)


class MiniRoute:
    """The route of a unit in one small line, as on the card but without dates."""

    @staticmethod
    def render(unit: Unit) -> str:
        stations = UnitRoute.build_stations(unit)
        marks = {"passed": "on", "reached": "now"}
        parts = []
        for index, station in enumerate(stations):
            css = marks.get(station.state, "")
            if station.state == "na":
                css = "na on" if station.is_passed else "na"
            if index:
                skipped = station.state == "na" or stations[index - 1].state == "na"
                is_on = station.state in marks or station.is_passed
                parts.append(
                    f'<i class="{"on " if is_on else ""}{"dashed" if skipped else ""}">'
                    "</i>"
                )
            parts.append(f'<b class="{css}"></b>')
        return f'<span class="mini">{"".join(parts)}</span>'


class UnitCards:
    """One block per unit: the top line, the route with dates, the post-release
    actions under it.
    """

    STOP_CSS = {"passed": "on", "reached": "now", "future": "", "na": "na"}
    ACTION_PILLS = {
        ActionStatus.PENDING: ("waits for check", "c-released"),
        ActionStatus.CONFIRMED: ("confirmed", "c-done"),
        ActionStatus.CANCELLED: ("cancelled", "c-gone"),
    }

    @classmethod
    def render(cls, view: WorkspaceView, item: Item) -> str:
        cards = "".join(
            cls._render_unit(view, item, u, n) for n, u in enumerate(item.work, 1)
        )
        return f'<div class="units">{cards}</div>'

    @classmethod
    def _render_unit(
        cls, view: WorkspaceView, item: Item, unit: Unit, number: int
    ) -> str:
        esc = HtmlText.esc
        stops = "".join(
            cls._render_stop(label, station)
            for label, station in zip(
                UnitRoute.PR_STATIONS, UnitRoute.build_stations(unit)
            )
        )
        actions = ""
        if isinstance(unit, PrUnit) and unit.post_release_actions:
            items = "".join(
                cls._render_action(unit, a) for a in unit.post_release_actions
            )
            actions = f'<ul class="acts">{items}</ul>'
        return (
            f'<article class="unit-card {UnitRoute.build_css(unit)}" '
            f'id="{Anchor.unit(unit.id)}"><div class="unit-top">'
            f'<span class="num">{number}.</span>'
            f'<span class="uname">{esc(unit.id)}</span>'
            f'<span class="tag">{esc(unit.kind)}</span>{cls._render_owner(view, item, unit)}'
            f"{ReasonText.unit_pill(unit)}</div>"
            f'<div class="route">{stops}</div>{actions}</article>'
        )

    @classmethod
    def _render_stop(cls, label: str, station: Station) -> str:
        css = cls.STOP_CSS[station.state]
        if station.state == "na":
            on = " on" if station.is_passed else ""
            return (
                f'<div class="stop na{on}"><span class="dot"></span>'
                f'<span class="lbl">{label}</span></div>'
            )
        when = (
            f'<span class="when">{station.when_html}</span>'
            if station.when_html
            else ""
        )
        return (
            f'<div class="stop {css}"><span class="dot"></span>'
            f'<span class="lbl">{label}</span>{when}</div>'
        )

    @classmethod
    def _render_owner(cls, view: WorkspaceView, item: Item, unit: Unit) -> str:
        esc = HtmlText.esc
        who = " · ".join(esc(assignee.short_text) for assignee in unit.assignees)
        who_html = f'<span class="who">{who}</span>' if who else ""
        if not isinstance(unit, PrUnit):
            return who_html or '<span class="who">no assignee</span>'
        if unit.pr is None:
            return f'<span class="who">no PR yet</span>{who_html}'
        return (
            HtmlText.pr_link(unit.pr)
            + cls._render_shared(view, item, unit, unit.pr)
            + who_html
        )

    @staticmethod
    def _render_shared(view: WorkspaceView, item: Item, unit: Unit, pr: PrRef) -> str:
        siblings = view.registry.find_units_sharing_pr(pr, item, unit)
        if not siblings:
            return ""
        links = ", ".join(
            f'<a href="{view.card_url(number, Anchor.unit(unit_id))}">'
            f"{sibling.address}</a>"
            for sibling in siblings
            for number, unit_id in [sibling.address.split("/")]
        )
        return f'<span class="who">shared with {links}</span>'

    @classmethod
    def _render_action(cls, unit: PrUnit, action: Action) -> str:
        esc = HtmlText.esc
        label, tone = cls.ACTION_PILLS[action.status]
        if action.is_failed:
            label, tone = "failed", "c-failed"
        elif action.status == ActionStatus.PENDING and unit.status == UnitStatus.MERGED:
            label, tone = "waits for release", "c-merged"
        detail = [PathLinks.html(action.instructions)]
        if action.confirmation is not None:
            confirmation = action.confirmation
            when = LocalDate.format(
                confirmation.observed_at or confirmation.recorded_at
            )
            detail.append(
                f"{esc(when)}: {PathLinks.html(confirmation.result)}"
                f" · source: {PathLinks.html(confirmation.source)}"
            )
        if action.status == ActionStatus.CANCELLED:
            detail.append(f"cancelled: {PathLinks.html(action.cancel_reason)}")
        findings = "".join(
            f'<span class="finding" id="{Anchor.finding(unit.id, action.id, number)}">'
            f"{LocalDate.html(finding.at)}: "
            f"{PathLinks.html(finding.text)}"
            f" · source: {PathLinks.html(finding.source)}</span>"
            for number, finding in enumerate(action.findings, 1)
        )
        return (
            f'<li id="{Anchor.action(unit.id, action.id)}">'
            f'<span class="aname">{esc(action.id)}</span>'
            f"{ReasonText.pill(label, tone)}"
            f'<span class="atitle">{PathLinks.html(action.description)}</span>'
            f'<span class="k">{esc(action.kind)}</span>'
            f'<span class="detail">{"<br>".join(detail)}</span>{findings}</li>'
        )


class CorrectionHistory:
    """Every merge or release record that was replaced, old values struck out."""

    SUBJECTS = {"merge": "merge", "release": "release"}

    @classmethod
    def render(cls, units: list[Unit]) -> str:
        entries = []
        for unit in units:
            if isinstance(unit, PrUnit):
                entries += [
                    (correction.at, cls._render_entry(unit, correction))
                    for correction in unit.corrections
                ]
        if not entries:
            return ""
        items = "".join(f"<li>{html}</li>" for _, html in sorted(entries))
        return (
            f'<details class="history"><summary>Corrections: {len(entries)}'
            f'</summary><ul class="hist">{items}</ul></details>'
        )

    @classmethod
    def _render_entry(cls, unit: PrUnit, correction: Correction) -> str:
        esc = HtmlText.esc
        chain = [c for c in unit.corrections if c.subject == correction.subject]
        later = chain[chain.index(correction) + 1 :]
        new = (
            cls._describe_old(later[0])
            if later
            else cls._describe_current(unit, correction)
        )
        return (
            f"{esc(unit.id)}, {cls.SUBJECTS[correction.subject]}: "
            f"<del>{cls._describe_old(correction)}</del> → {new} · reason: "
            f"{PathLinks.html(correction.reason)} · {LocalDate.html(correction.at)}"
        )

    @classmethod
    def _describe_old(cls, correction: Correction) -> str:
        source = correction.old_evidence.source if correction.old_evidence else None
        return cls._join(
            correction.old_pr, correction.old_at, correction.old_tag, source
        )

    @classmethod
    def _describe_current(cls, unit: PrUnit, correction: Correction) -> str:
        if correction.subject == "merge" and unit.merge is not None:
            return cls._join(
                unit.pr, unit.merge.merged_at, None, unit.merge.evidence.source
            )
        if unit.release is not None:
            release = unit.release
            return cls._join(
                None, release.released_at, release.tag, release.evidence.source
            )
        return ""

    @staticmethod
    def _join(pr: object, at: str | None, tag: str | None, source: str | None) -> str:
        parts = [
            HtmlText.esc(pr) if pr else "",
            LocalDate.html(at) if at else "",
            f"tag {HtmlText.esc(tag)}" if tag else "",
            f"source {HtmlText.esc(source)}" if source else "",
        ]
        return ", ".join(part for part in parts if part) or "nothing"
