from __future__ import annotations


class ResultOwnerIndex:
    def __init__(self) -> None:
        self._owner_result_ids: dict[str, str] = {}
        self._result_owners: dict[str, str] = {}

    @property
    def owner_result_ids(self) -> dict[str, str]:
        return self._owner_result_ids

    @property
    def result_owners(self) -> dict[str, str]:
        return self._result_owners

    def get_result_id(self, owner_key: str) -> str | None:
        return self._owner_result_ids.get(owner_key)

    def remember(self, *, owner_key: str, result_id: str) -> None:
        if not owner_key:
            return
        self._owner_result_ids[owner_key] = result_id
        self._result_owners[result_id] = owner_key

    def forget_result(self, result_id: str) -> None:
        owner_key = self._result_owners.pop(result_id, None)
        if owner_key and self._owner_result_ids.get(owner_key) == result_id:
            self._owner_result_ids.pop(owner_key, None)

    @staticmethod
    def normalize_owner_key(owner_key: str | None) -> str:
        return str(owner_key or "").strip().casefold()
