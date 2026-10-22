from dataclasses import dataclass, field

from django.db.models import F, QuerySet

from tournament.models import MedalCategory, MedalType, Player, PlayerMedal, Season, Team, TeamMedal


@dataclass(frozen=True)
class CategorizedMedalGroup:
    category: MedalCategory | None
    grants: list[PlayerMedal]
    career_medals: list[MedalType] = field(default_factory=list)

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
    career_medals: list[MedalType] = field(default_factory=list)

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
            'medal__medal_type__category',
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            F('medal__medal_type__category__order').asc(nulls_last=True),
            'medal__medal_type__category_id',
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
            'medal__medal_type__category',
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            F('medal__medal_type__category__order').asc(nulls_last=True),
            'medal__medal_type__category_id',
            F('awarded_at').desc(nulls_last=True),
            F('medal__season__number').desc(nulls_last=True),
            '-medal_id',
        )
    )
    groups = []
    current_category_id = object()
    current_group = None

    for grant in grants:
        category = grant.medal.medal_type.category
        category_id = category.pk if category else None
        if category_id != current_category_id:
            current_category_id = category_id
            current_group = CategorizedMedalGroup(category=category, grants=[])
            groups.append(current_group)
        current_group.grants.append(grant)

    _add_career_medal_reference(groups)
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
            'medal__medal_type__category',
            'medal__medal_type',
            'medal__season',
            'medal__league',
        )
        .order_by(
            F('medal__medal_type__category__order').asc(nulls_last=True),
            'medal__medal_type__category_id',
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
        category = grant.medal.medal_type.category
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

    _add_career_medal_reference(categories)
    return StructuredMedalCollection(categories=categories, total_count=total_count)


def _add_career_medal_reference(groups):
    if not groups:
        return
    groups_by_category = {group.category.pk if group.category else None: group for group in groups}
    unit_order = {
        MedalType.Unit.MATCHES: 0,
        MedalType.Unit.GOALS: 1,
        MedalType.Unit.ASSISTS: 2,
        MedalType.Unit.CLEAN_SHEETS: 3,
    }
    medals = MedalType.objects.filter(kind=MedalType.Kind.CAREER_MILESTONE).order_by('unit', 'threshold', 'pk')
    for medal_type in sorted(medals, key=lambda medal: unit_order.get(medal.unit, len(unit_order))):
        group = groups_by_category.get(medal_type.category_id)
        if group is not None:
            group.career_medals.append(medal_type)
