#!/usr/bin/env python
"""Fill the database with realistic demo data, so a fresh deployment is not empty.

    python scripts/seed_demo.py            # seed (safe to run repeatedly)
    python scripts/seed_demo.py --reset    # remove the demo accounts and their data

Inside Docker:

    docker compose exec api python scripts/seed_demo.py

Everything goes through the app's own service and repository layer, so each
item's lifecycle history, claim decisions and notifications are written exactly
as they would be through the API. The one shortcut is account creation: demo
users are created already verified, via ``UserRepository``, rather than through
``AuthService.register`` -- that path issues an OTP and, with MAIL_ENABLED=true,
would try to email it.

Demo data is identified by the fixed list of ``@example.com`` accounts in
``DEMO_USERS``. ``--reset`` deletes exactly those accounts; their items, claims
and notifications follow by ON DELETE CASCADE. No other account is touched.
Locations and categories are kept: they are shared taxonomy that real items may
already reference, and nothing in the schema records who created them.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.lifecycle import ItemKind, ItemStatus  # noqa: E402
from app.repositories.claim_repo import ClaimRepository  # noqa: E402
from app.repositories.item_repo import ItemRepository  # noqa: E402
from app.repositories.location_repo import CategoryRepository, LocationRepository  # noqa: E402
from app.repositories.user_repo import UserRepository  # noqa: E402
from app.schemas.claim import ClaimCreateRequest, ClaimDecisionRequest  # noqa: E402
from app.schemas.item import ItemCreateRequest, StatusTransitionRequest  # noqa: E402
from app.schemas.location import CategoryCreateRequest, LocationCreateRequest  # noqa: E402
from app.services.claim_service import ClaimService  # noqa: E402
from app.services.item_service import ItemService  # noqa: E402
from app.services.location_service import LocationService  # noqa: E402

#: Shared by every demo account. Public on purpose -- these are for visitors.
DEMO_PASSWORD = "campus-demo-2026"


@dataclass(frozen=True)
class DemoUser:
    key: str
    first_name: str
    last_name: str
    roll_number: str
    batch: int
    course: str
    branch: str

    @property
    def email(self) -> str:
        # example.com is reserved (RFC 2606): nothing sent here reaches a person.
        return f"{self.first_name.lower()}.{self.last_name.lower()}@example.com"


@dataclass(frozen=True)
class DemoItem:
    reporter: str
    kind: ItemKind
    name: str
    description: str
    category: str
    location: str
    days_ago: int
    #: What happens after the item is reported, in order. Each step is one of
    #:   ("claim",   <user key>, evidence)   -- that user files a claim
    #:   ("approve", <user key>, note)       -- reporter approves their claim
    #:   ("reject",  <user key>, note)       -- reporter rejects their claim
    #:   ("move",    <status>,   note)       -- reporter transitions the item
    steps: tuple[tuple[str, str, str | None], ...] = field(default=())


DEMO_USERS = (
    DemoUser("aarav", "Aarav", "Mehta", "21CS1043", 2025, "BTECH", "CSE"),
    DemoUser("priya", "Priya", "Nair", "22EC2017", 2026, "BTECH", "ECE"),
    DemoUser("rohan", "Rohan", "Gupta", "23ME3108", 2027, "BTECH", "ME"),
    DemoUser("sneha", "Sneha", "Iyer", "23MB0412", 2025, "MBA", "FIN"),
    DemoUser("kabir", "Kabir", "Singh", "24CE1055", 2028, "BTECH", "CIVIL"),
    DemoUser("ananya", "Ananya", "Das", "23PH5021", 2025, "MSC", "PHY"),
)

#: key -> (name, building, description)
DEMO_LOCATIONS = {
    "library": ("Reading Hall", "Central Library",
                "Silent study area on the second floor, next to the periodicals."),
    "canteen": ("Main Canteen", "Student Activity Centre",
                "Ground-floor canteen; lost property goes to the billing counter."),
    "hostel3": ("Common Room", "Hostel 3",
                "TV and games room on the ground floor of Hostel 3."),
    "hostel7": ("Mess Hall", "Hostel 7", "Dining hall shared by Hostels 6 and 7."),
    "sports": ("Badminton Courts", "Sports Complex",
               "Indoor courts and spectator bleachers."),
    "cselab": ("Computer Lab 2", "CSE Department", "Second-floor lab, desks 1-40."),
    "chemlab": ("Organic Chemistry Lab", "Science Block", "First-floor teaching lab."),
    "lecture": ("LH-101", "Academic Block A", "Largest lecture hall, 240 seats."),
}

DEMO_CATEGORIES = (
    "Electronics", "ID Cards", "Keys", "Bags", "Books", "Clothing", "Bottles", "Other",
)

FOUND, LOST = ItemKind.FOUND, ItemKind.LOST

DEMO_ITEMS = (
    # --- found items with claims -------------------------------------------
    DemoItem(
        "priya", FOUND, "Black JBL earbuds case, scratch on lid",
        "JBL Tune Buds charging case, black, with a long scratch across the lid. "
        "No earbuds inside. Picked up from the table next to the window.",
        "Electronics", "library", 2,
        steps=(
            ("claim", "rohan", "The scratch is from my hostel keys. The case pairs as "
                               "'Rohan's Buds' and I can show it in the JBL app."),
        ),
    ),
    DemoItem(
        "kabir", FOUND, "Student ID card on a blue lanyard",
        "College ID card on a blue lanyard, photo slightly faded, name partly "
        "visible as 'Ananya D.'. Found near the canteen billing counter.",
        "ID Cards", "canteen", 6,
        steps=(
            ("claim", "ananya", "It's my ID, roll number 23PH5021. The lanyard has a "
                                "small metal cat keyring on it."),
            ("approve", "ananya", "Roll number and keyring both match."),
        ),
    ),
    DemoItem(
        "sneha", FOUND, "Three keys on a red Manchester United keyring",
        "Two brass keys and one small silver locker key on a red Manchester United "
        "keyring with a bottle opener. Found by the court 3 bench.",
        "Keys", "sports", 12,
        steps=(
            ("claim", "aarav", "Hostel room key, cycle lock key and my gym locker key "
                               "(locker 47). The bottle opener is chipped on one side."),
            ("approve", "aarav", "Locker 47 key checked with the sports office."),
            ("move", "closed", "Handed over at the Sports Complex front desk."),
        ),
    ),
    DemoItem(
        "aarav", FOUND, "Casio fx-991EX calculator",
        "Casio fx-991EX ClassWiz, grey, with initials scratched into the back "
        "cover. Left on a bench after the thermodynamics quiz.",
        "Electronics", "lecture", 9,
        steps=(
            ("claim", "kabir", "I lost a Casio calculator after my quiz in LH-101."),
            # Its only claim rejected, the item goes back to 'reported' by itself.
            ("reject", "kabir", "Claimant could not describe the initials on the back."),
        ),
    ),
    DemoItem(
        "rohan", FOUND, "Grey Nike hoodie, size M",
        "Grey Nike Club fleece hoodie, size M, with a faded blue paint stain on the "
        "right cuff. Left on the bleachers after evening practice.",
        "Clothing", "sports", 4,
        steps=(
            ("claim", "priya", "I lost a grey hoodie at the courts last week."),
            ("claim", "sneha", "Size M Nike Club hoodie -- the blue paint on the right "
                               "cuff is from Holi, and my initials are on the hood tag."),
            ("reject", "priya", None),
            ("approve", "sneha", "Initials on the hood tag match."),
        ),
    ),
    DemoItem(
        "ananya", FOUND, "Steel Milton water bottle, 1L, dented",
        "Silver Milton Thermosteel bottle, 1 litre, dented near the base, with a "
        "NASA sticker and a Coding Club sticker.",
        "Bottles", "cselab", 1,
        steps=(
            ("claim", "kabir", "The Coding Club sticker is from orientation, and the "
                               "dent is from dropping it on the lab stairs."),
        ),
    ),
    DemoItem(
        "sneha", FOUND, "Higher Engineering Mathematics by B.S. Grewal",
        "44th edition, pencil notes in chapters 1-4, an old metro card being used "
        "as a bookmark.",
        "Books", "library", 15,
        steps=(
            ("claim", "rohan", "My Grewal -- the metro card is my bookmark, and my "
                               "Laplace transform notes are on page 312."),
            ("approve", "rohan", "Notes on p.312 confirmed."),
        ),
    ),
    # --- found items still waiting for an owner ----------------------------
    DemoItem(
        "kabir", FOUND, "Navy Wildcraft backpack, broken front zip",
        "Navy-blue Wildcraft backpack; the front pocket zip is broken. Contains a "
        "lab coat and a geometry box.",
        "Bags", "chemlab", 3,
    ),
    DemoItem(
        "priya", FOUND, "Single silver hoop earring",
        "Small silver hoop earring, about 2 cm across, found on the floor near the "
        "wash basins.",
        "Other", "hostel7", 5,
    ),
    DemoItem(
        "ananya", FOUND, "Lenovo 65W USB-C laptop charger",
        "Lenovo 65W USB-C charger; the cable is wrapped in black electrical tape "
        "near the plug. Left plugged in at desk 14.",
        "Electronics", "cselab", 0,
    ),
    DemoItem(
        "aarav", FOUND, "Navy college blazer, size 40",
        "Navy blazer with the college crest on the pocket, size 40. Left over a "
        "chair in the front row after Friday's seminar.",
        "Clothing", "lecture", 7,
    ),
    DemoItem(
        "rohan", FOUND, "Black-framed glasses in a brown Lenskart case",
        "Rectangular black-framed prescription glasses in a brown Lenskart hard "
        "case. Found on table 9 after dinner.",
        "Other", "hostel7", 10,
    ),
    DemoItem(
        "sneha", FOUND, "Room key on green tag marked B-214",
        "Single key on a green plastic tag marked 'B-214'. Found on the floor by "
        "the carrom board.",
        "Keys", "hostel3", 8,
    ),
    DemoItem(
        "kabir", FOUND, "Purple Tupperware lunch box",
        "Purple two-compartment Tupperware lunch box with a steel spoon inside. "
        "Left at table 6.",
        "Other", "canteen", 1,
    ),
    # --- lost items: still looking ------------------------------------------
    DemoItem(
        "aarav", LOST, "AirPods Pro in a blue silicone cover",
        "White AirPods Pro case in a blue silicone cover with a small carabiner. "
        "Probably dropped between the library and the canteen around 4 pm.",
        "Electronics", "library", 3,
    ),
    DemoItem(
        "priya", LOST, "Maroon leather bifold wallet",
        "Maroon leather bifold wallet with my college ID and some cash. Last had it "
        "while paying at the canteen counter.",
        "Other", "canteen", 2,
    ),
    DemoItem(
        "rohan", LOST, "SG cricket kit bag, black and red",
        "SG kit bag, black and red, with a Kashmir willow bat and batting gloves "
        "inside. Left near the nets after Sunday practice.",
        "Bags", "sports", 11,
    ),
    DemoItem(
        "ananya", LOST, "Organic chemistry lab record, brown cover",
        "Hard-bound lab record with a brown cover; name and roll number on the "
        "first page. Every experiment from this semester is in it.",
        "Books", "chemlab", 6,
    ),
    DemoItem(
        "kabir", LOST, "Silver Titan analog watch",
        "Titan watch, silver metal strap, white dial. Took it off before a "
        "badminton match and haven't seen it since.",
        "Other", "sports", 14,
    ),
    # --- lost items: a possible match has turned up --------------------------
    DemoItem(
        "sneha", LOST, "Black 15-inch laptop sleeve",
        "Black neoprene laptop sleeve with a small tear at one corner; has printouts "
        "of my corporate finance assignment inside.",
        "Bags", "lecture", 5,
        steps=(
            ("move", "matched", "Security says a black sleeve was handed in on "
                                "Tuesday -- going to check."),
        ),
    ),
    DemoItem(
        "aarav", LOST, "Blue Milton bottle with dinosaur stickers",
        "Blue 750 ml Milton bottle covered in dinosaur stickers; the cap has a "
        "cracked loop.",
        "Bottles", "hostel3", 8,
        steps=(
            ("move", "matched", "Someone posted a photo of a blue bottle in the "
                                "Hostel 3 group -- looks like mine."),
        ),
    ),
    DemoItem(
        "priya", LOST, "Black JanSport backpack with a panda keychain",
        "Black JanSport backpack, panda keychain on the zip, a Signals and Systems "
        "notebook inside.",
        "Bags", "library", 13,
        steps=(
            ("move", "matched", "Library staff have a black JanSport in the lost "
                                "property cupboard with a panda keychain."),
        ),
    ),
    # --- lost items: resolved -------------------------------------------------
    DemoItem(
        "rohan", LOST, "Grey boAt Rockerz headphones",
        "Grey boAt Rockerz 450 over-ear headphones, left ear cushion slightly torn.",
        "Electronics", "hostel3", 20,
        steps=(("move", "closed", "Found them under my roommate's bed. Sorry!"),),
    ),
    DemoItem(
        "ananya", LOST, "Pink Cello insulated bottle",
        "Pink Cello Puro insulated bottle, 900 ml, name written on masking tape on "
        "the bottom.",
        "Bottles", "lecture", 18,
        steps=(("move", "closed", "It was at the Academic Block A reception desk."),),
    ),
    DemoItem(
        "kabir", LOST, "Central Library borrower card",
        "Library borrower card in a clear plastic sleeve. Needed to return two "
        "books before the due date.",
        "ID Cards", "library", 25,
        steps=(("move", "closed", "Library issued a replacement card, so this can "
                                  "be closed."),),
    ),
)

#: (lost, found) posts about the same object, written by different people, so
#: the item page's "Possible matches" panel has something to show. Each pair
#: scores well above the suggestion threshold (0.52-0.80 against 0.25).
DEMO_PAIRS = (
    (
        DemoItem(
            "kabir", LOST, "Grey Logitech M235 wireless mouse",
            "Grey Logitech M235 wireless mouse; the USB receiver is tucked into the "
            "battery slot. Left at a desk after the evening lab.",
            "Electronics", "cselab", 4,
        ),
        DemoItem(
            "priya", FOUND, "Logitech wireless mouse, grey",
            "Grey Logitech M235 mouse left next to the monitor at desk 22, USB "
            "receiver inside the battery compartment.",
            "Electronics", "cselab", 3,
            # The owner spotted it under "Possible matches" and claimed it.
            steps=(
                ("claim", "kabir", "It's my M235 -- the receiver lives in the battery "
                                   "slot and the left button sticks slightly."),
            ),
        ),
    ),
    (
        DemoItem(
            "ananya", LOST, "Scooty key on a Hello Kitty keychain",
            "Honda Activa key on a pink Hello Kitty keychain, with a small brass "
            "padlock key. Dropped somewhere near the mess counter.",
            "Keys", "hostel7", 7,
        ),
        DemoItem(
            "rohan", FOUND, "Honda scooter key with Hello Kitty keychain",
            "Honda key on a pink Hello Kitty keychain plus a tiny brass key. Found "
            "under a bench outside the mess.",
            "Keys", "hostel7", 6,
        ),
    ),
    (
        DemoItem(
            "priya", LOST, "Black Puma track jacket, size L",
            "Black Puma track jacket with white stripes down the sleeves, size L. "
            "Left on the bleachers after badminton practice.",
            "Clothing", "sports", 9,
        ),
        DemoItem(
            "aarav", FOUND, "Black Puma track jacket with white stripes",
            "Black Puma zip-up track jacket, white sleeve stripes, size L. Found "
            "folded on the bleachers.",
            "Clothing", "sports", 8,
        ),
    ),
    (
        DemoItem(
            "rohan", LOST, "H.C. Verma Concepts of Physics Vol. 1",
            "Blue-covered Concepts of Physics, Volume 1, my name inside the front "
            "cover and sticky notes in the optics chapter.",
            "Books", "lecture", 5,
        ),
        DemoItem(
            "sneha", FOUND, "Concepts of Physics Vol. 1 by H.C. Verma",
            "H.C. Verma Volume 1, blue cover, yellow sticky notes in the optics "
            "chapter. Left under a seat.",
            "Books", "lecture", 2,
        ),
    ),
)

DEMO_ITEMS += tuple(item for pair in DEMO_PAIRS for item in pair)


@dataclass
class SeedReport:
    users_created: int = 0
    locations_created: int = 0
    categories_created: int = 0
    items_created: int = 0
    claims_created: int = 0
    item_status: Counter = field(default_factory=Counter)
    claim_status: Counter = field(default_factory=Counter)


@dataclass
class ResetReport:
    users_deleted: int = 0
    items_deleted: int = 0
    claims_deleted: int = 0
    #: Claims deleted along with demo data that involved a non-demo account --
    #: e.g. a real user claiming a demo item. Reported so it is never a surprise.
    foreign_claims_deleted: int = 0


# --- seeding --------------------------------------------------------------

def seed(db: Session) -> SeedReport:
    """Create whatever demo data is missing. Does not commit."""
    report = SeedReport()
    users = _seed_users(db, report)
    locations, categories = _seed_taxonomy(db, report)

    item_service = ItemService(db)
    claim_service = ClaimService(db)
    item_repo = ItemRepository(db)
    today = date.today()

    for spec in DEMO_ITEMS:
        reporter = users[spec.reporter]
        if _find_item(item_repo, reporter, spec.name) is not None:
            continue
        item = item_service.register_item(
            ItemCreateRequest(
                name=spec.name,
                description=spec.description,
                kind=spec.kind,
                occurred_on=today - timedelta(days=spec.days_ago),
                category_id=categories[spec.category],
                location_id=locations[spec.location],
            ),
            reporter,
        )
        report.items_created += 1

        claims = {}
        for action, target, text in spec.steps:
            if action == "claim":
                claims[target] = claim_service.file_claim(
                    item.id, ClaimCreateRequest(evidence=text), users[target]
                )
                report.claims_created += 1
            elif action in ("approve", "reject"):
                claim_service.decide(
                    claims[target].id,
                    ClaimDecisionRequest(approve=action == "approve", note=text),
                    reporter,
                )
            elif action == "move":
                item_service.transition_status(
                    item.id,
                    StatusTransitionRequest(to_status=ItemStatus(target), note=text),
                    reporter,
                )
            else:  # pragma: no cover - a typo in DEMO_ITEMS
                raise ValueError(f"Unknown demo step {action!r} on {spec.name!r}.")

    _tally(db, users.values(), report)
    return report


def _seed_users(db: Session, report: SeedReport) -> dict[str, User]:
    repo = UserRepository(db)
    users = {}
    for demo in DEMO_USERS:
        user = repo.get_by_email(demo.email)
        if user is None:
            user = repo.create(
                email=demo.email,
                password_hash=hash_password(DEMO_PASSWORD),
                first_name=demo.first_name,
                last_name=demo.last_name,
                roll_number=demo.roll_number,
                batch=demo.batch,
                course=demo.course,
                branch=demo.branch,
                is_verified=True,
                is_admin=False,
            )
            report.users_created += 1
        elif user.is_admin:
            # The password is public, so a demo admin would be an open door.
            repo.set_admin(user, False)
            print(f"Warning: {user.email} was an admin; access revoked.", file=sys.stderr)
        users[demo.key] = user
    return users


def _seed_taxonomy(db: Session, report: SeedReport) -> tuple[dict[str, int], dict[str, int]]:
    service = LocationService(db)
    location_repo = LocationRepository(db)

    locations = {}
    for key, (name, building, description) in DEMO_LOCATIONS.items():
        location = location_repo.get_by_name(name, building)
        if location is None:
            location = service.create_location(LocationCreateRequest(
                name=name, building=building, description=description,
            ))
            report.locations_created += 1
        locations[key] = location.id

    # Match existing categories case-insensitively, so a real "electronics"
    # category is reused rather than shadowed by a near-duplicate.
    _, existing = CategoryRepository(db).list_all()
    by_name = {c.name.lower(): c for c in existing}
    categories = {}
    for name in DEMO_CATEGORIES:
        category = by_name.get(name.lower())
        if category is None:
            category = service.create_category(CategoryCreateRequest(name=name))
            report.categories_created += 1
        categories[name] = category.id
    return locations, categories


def _find_item(repo: ItemRepository, reporter: User, name: str):
    """The demo item with this exact name, if its reporter already has it."""
    _, candidates = repo.search(q=name, reporter_id=reporter.id, limit=100)
    return next((item for item in candidates if item.name == name), None)


def _tally(db: Session, users, report: SeedReport) -> None:
    items = ItemRepository(db)
    claims = ClaimRepository(db)
    for user in users:
        _, reported = items.search(reporter_id=user.id, limit=1000)
        report.item_status.update(item.status.value for item in reported)
        _, filed = claims.search(claimant_id=user.id, limit=1000)
        report.claim_status.update(claim.status.value for claim in filed)


# --- reset ----------------------------------------------------------------

def reset(db: Session) -> ResetReport:
    """Delete the demo accounts and, by cascade, everything they own. Does not commit."""
    report = ResetReport()
    users = UserRepository(db)
    items = ItemRepository(db)
    claims = ClaimRepository(db)

    demo = [u for u in (users.get_by_email(d.email) for d in DEMO_USERS) if u is not None]
    demo_ids = {u.id for u in demo}

    touched = {}
    for user in demo:
        report.items_deleted += items.search(reporter_id=user.id, limit=1)[0]
        _, rows = claims.search(visible_to_id=user.id, limit=10_000)
        touched.update((claim.id, claim) for claim in rows)
    report.claims_deleted = len(touched)
    report.foreign_claims_deleted = sum(
        1 for claim in touched.values()
        if claim.claimant_id not in demo_ids or claim.item.reporter_id not in demo_ids
    )

    for user in demo:
        users.delete(user)
        report.users_deleted += 1
    return report


# --- cli --------------------------------------------------------------------

def _print_seed_report(report: SeedReport) -> None:
    print("Demo data seeded.")
    print(f"  created: {report.users_created} users, {report.locations_created} locations, "
          f"{report.categories_created} categories, {report.items_created} items, "
          f"{report.claims_created} claims")
    if not any((report.users_created, report.locations_created,
                report.categories_created, report.items_created)):
        print("  (everything was already present -- nothing new to add)")
    items = ", ".join(f"{report.item_status[s.value]} {s.value}" for s in ItemStatus)
    claims = ", ".join(f"{n} {s}" for s, n in sorted(report.claim_status.items()))
    print(f"  demo items: {sum(report.item_status.values())} ({items})")
    print(f"  demo claims: {sum(report.claim_status.values())} ({claims or 'none'})")
    print()
    print("Demo logins (all verified, none are admins):")
    for demo in DEMO_USERS:
        print(f"  {demo.email}")
    print(f"Shared password: {DEMO_PASSWORD}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Delete the demo accounts and everything they own, then exit.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        try:
            if args.reset:
                result = reset(db)
                db.commit()
            else:
                result = seed(db)
                db.commit()
        except Exception:
            db.rollback()
            raise

    if args.reset:
        print(f"Removed {result.users_deleted} demo users, {result.items_deleted} items "
              f"and {result.claims_deleted} claims.")
        if result.foreign_claims_deleted:
            print(f"  {result.foreign_claims_deleted} of those claims involved a "
                  "non-demo account (e.g. a real user claiming a demo item).")
        print("Locations and categories were kept.")
    else:
        _print_seed_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
