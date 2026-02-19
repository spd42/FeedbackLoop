from __future__ import annotations

from datetime import datetime, timedelta
import requests

from .models import FailedCard


class AnkiConnectClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def _invoke(self, action: str, **params):
        payload = {"action": action, "version": 6, "params": params}
        resp = requests.post(self.base_url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        return data.get("result")

    def recent_failed_cards(self, lookback_days: int, limit: int) -> list[FailedCard]:
        min_epoch = int((datetime.now() - timedelta(days=lookback_days)).timestamp())
        query = f"rated:{lookback_days}:1"

        card_ids = self._invoke("findCards", query=query) or []
        if not card_ids:
            return []

        card_ids = card_ids[: limit * 2]
        cards = self._invoke("cardsInfo", cards=card_ids) or []

        failed_card_ids = {}
        try:
            reviews = self._invoke("getReviewsOfCards", cards=card_ids) or {}
            for cid_str, entries in reviews.items():
                for rev in entries or []:
                    # revlog ease=1 corresponds to "Again" (incorrect/failed recall).
                    if (
                        int(rev.get("id", 0) // 1000) >= min_epoch
                        and int(rev.get("ease", 0)) == 1
                    ):
                        cid = int(cid_str)
                        failed_card_ids[cid] = failed_card_ids.get(cid, 0) + 1
                        break
        except Exception:
            failed_card_ids = []

        out: list[FailedCard] = []
        for c in cards:
            cid = int(c.get("cardId", 0))
            if failed_card_ids and cid not in failed_card_ids:
                continue
            if not failed_card_ids:
                interval = c.get("interval", 0)
                if interval > 10:
                    continue
            fields = c.get("fields", {})
            values = []
            for f in fields.values():
                val = (f or {}).get("value", "").strip()
                if val:
                    values.append(val)

            front = values[0] if len(values) >= 1 else ""
            back = values[1] if len(values) >= 2 else ""
            if front or back:
                weight = failed_card_ids.get(cid, 1)
                for _ in range(weight):
                    out.append(FailedCard(front=front, back=back))
            if len(out) >= limit:
                break

        return out
