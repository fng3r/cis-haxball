from dataclasses import dataclass

from django.db.models import F, QuerySet

from tournament.models import MedalType, Player, PlayerMedal, Team, TeamMedal


@dataclass(frozen=True)
class StructuredMedalGroup:
    medal_type: MedalType
    grants: list[PlayerMedal | TeamMedal]

    @property
    def count(self):
        return len(self.grants)


@dataclass(frozen=True)
class StructuredMedalCollection:
    groups: list[StructuredMedalGroup]
    total_count: int

    @property
    def type_count(self):
        return len(self.groups)


def get_player_medals(player: Player) -> StructuredMedalCollection:
    grants = (
        PlayerMedal.objects.filter(player=player)
        .select_related(
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            'medal__medal_type__order',
            'medal__medal_type__code',
            F('medal__season__number').desc(nulls_last=True),
            '-medal_id',
        )
    )
    return _group_medals(grants)


def get_team_medals(team: Team) -> StructuredMedalCollection:
    grants = (
        TeamMedal.objects.filter(team=team)
        .select_related(
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            'medal__medal_type__order',
            'medal__medal_type__code',
            F('medal__season__number').desc(nulls_last=True),
            '-medal_id',
        )
    )
    return _group_medals(grants)


def _group_medals(grants: QuerySet[PlayerMedal] | QuerySet[TeamMedal]) -> StructuredMedalCollection:
    groups = []
    current_type_id = None
    current_group = None
    total_count = 0

    for grant in grants:
        total_count += 1
        medal_type = grant.medal.medal_type
        if medal_type.pk != current_type_id:
            current_type_id = medal_type.pk
            current_group = StructuredMedalGroup(medal_type=medal_type, grants=[])
            groups.append(current_group)
        current_group.grants.append(grant)

    return StructuredMedalCollection(groups=groups, total_count=total_count)
