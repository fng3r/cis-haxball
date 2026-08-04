from dataclasses import dataclass

from django.db.models import F, QuerySet

from tournament.models import MedalCategory, MedalType, Player, PlayerMedal, Season, Team, TeamMedal


@dataclass(frozen=True)
class CategorizedMedalGroup:
    category: MedalCategory | None
    grants: list[PlayerMedal]

    @property
    def title(self):
        return self.category.title if self.category else 'Без категории'


@dataclass(frozen=True)
class CategorizedMedalCollection:
    groups: list[CategorizedMedalGroup]
    total_count: int


@dataclass(frozen=True)
class StructuredMedalGroup:
    medal_type: MedalType
    grants: list[PlayerMedal | TeamMedal]

    @property
    def count(self):
        return len(self.grants)


@dataclass(frozen=True)
class StructuredMedalCategoryGroup:
    category: MedalCategory | None
    groups: list[StructuredMedalGroup]

    @property
    def title(self):
        return self.category.title if self.category else 'Без категории'


@dataclass(frozen=True)
class StructuredMedalCollection:
    categories: list[StructuredMedalCategoryGroup]
    total_count: int

    @property
    def type_count(self):
        return len({group.medal_type.pk for category in self.categories for group in category.groups})


def get_player_medals(player: Player) -> StructuredMedalCollection:
    grants = (
        PlayerMedal.objects.filter(player=player)
        .select_related(
            'medal__category',
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            F('medal__category__order').asc(nulls_last=True),
            'medal__category_id',
            'medal__medal_type__order',
            'medal__medal_type__code',
            F('medal__season__number').desc(nulls_last=True),
            '-medal_id',
        )
    )
    return _group_medals(grants)


def get_player_medals_by_category(player: Player) -> CategorizedMedalCollection:
    grants = (
        PlayerMedal.objects.filter(player=player)
        .select_related(
            'medal__category',
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            F('medal__category__order').asc(nulls_last=True),
            'medal__category_id',
            F('awarded_at').desc(nulls_last=True),
            F('medal__season__number').desc(nulls_last=True),
            '-medal_id',
        )
    )
    groups = []
    current_category_id = object()
    current_group = None

    for grant in grants:
        category = grant.medal.category
        category_id = category.pk if category else None
        if category_id != current_category_id:
            current_category_id = category_id
            current_group = CategorizedMedalGroup(category=category, grants=[])
            groups.append(current_group)
        current_group.grants.append(grant)

    return CategorizedMedalCollection(groups=groups, total_count=sum(len(group.grants) for group in groups))


def get_team_medals_by_season(team: Team) -> list[tuple[Season | None, list[TeamMedal]]]:
    grants = (
        TeamMedal.objects.filter(team=team)
        .select_related(
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            'medal__season__number',
            'medal__medal_type__order',
            'medal_id',
        )
    )
    season_groups = []
    current_season_id = object()
    current_grants = None
    for grant in grants:
        if grant.medal.season_id != current_season_id:
            current_season_id = grant.medal.season_id
            current_grants = []
            season_groups.append((grant.medal.season, current_grants))
        current_grants.append(grant)
    return season_groups


def get_team_medals(team: Team) -> StructuredMedalCollection:
    grants = (
        TeamMedal.objects.filter(team=team)
        .select_related(
            'medal__category',
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            F('medal__category__order').asc(nulls_last=True),
            'medal__category_id',
            'medal__medal_type__order',
            'medal__medal_type__code',
            F('medal__season__number').desc(nulls_last=True),
            '-medal_id',
        )
    )
    return _group_medals(grants)


def _group_medals(grants: QuerySet[PlayerMedal] | QuerySet[TeamMedal]) -> StructuredMedalCollection:
    categories = []
    current_category_id = object()
    current_category = None
    current_type_id = object()
    current_group = None
    total_count = 0

    for grant in grants:
        total_count += 1
        category = grant.medal.category
        category_id = category.pk if category else None
        if category_id != current_category_id:
            current_category_id = category_id
            current_category = StructuredMedalCategoryGroup(category=category, groups=[])
            categories.append(current_category)
            current_type_id = object()

        medal_type = grant.medal.medal_type
        if medal_type.pk != current_type_id:
            current_type_id = medal_type.pk
            current_group = StructuredMedalGroup(medal_type=medal_type, grants=[])
            current_category.groups.append(current_group)
        current_group.grants.append(grant)

    return StructuredMedalCollection(categories=categories, total_count=total_count)
