"""The route table: every page the generator writes, with its title, description, H1, indexing, ad eligibility,
scripts and the data dates behind its "Updated" line.

Titles, descriptions and H1s may hold {placeholders} filled from facts(D), so counts never go stale.
"""
from dataclasses import dataclass, field, replace

from .data import TOWN_SLUGS
from .fmt import num

BRAND = " · NK15068"


@dataclass(frozen=True)
class Route:
    path: str            # "/crime/arnold/" (directory routes) or "/404.html"
    page: str            # page_id, also <html data-page>
    title: str
    desc: str
    h1: str
    index: str           # "I" indexable, "N" noindex, "NF" noindex,follow
    ads: str             # "C" may carry ad slots once configured, "-" never
    scripts: tuple       # script keys, see SCRIPTS
    dates: tuple         # keys of data.DATES behind the page's Updated date
    mod: str             # nkpages module holding the page function
    fn: str              # page function: fn(D, R) -> str | dict
    arg: str = None      # e.g. the town slug for per-town pages
    nav: str = None      # which bar link is current ("lost-pets", "numbers", "calendar", "crime", "map", "towns", …)
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    @property
    def depth(self):
        return 0 if self.path == "/404.html" else self.path.strip("/").count("/") + (1 if self.path != "/" else 0)

    @property
    def root(self):
        return "../" * self.depth

    @property
    def file(self):
        return "404.html" if self.path == "/404.html" else (self.path.lstrip("/") + "index.html")


# script key -> src (relative to the site root) ; three.js stays r128 from cdnjs
SCRIPTS = {
    "three": "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js",
    "pubs": "assets/pubs.js", "nkmap": "assets/nkmap.js", "nk3d": "assets/nk3d.js", "safety": "assets/safety.js",
    "pets": "assets/pets.js", "search": "assets/search.js", "app": "assets/app.js",
}

S_HOME = ("pubs", "pets", "app")
S_BASIC = ("pubs", "app")
S_CRIME = ("pubs", "safety", "app")
ALL_DATES = ("meta", "civic", "history", "pets", "safety", "changelog")

TOWN_NAMES = {v: k for k, v in TOWN_SLUGS.items()}


def facts(D):
    """Counts and year spans used in titles and descriptions."""
    s = D["safety"]
    years = [y["year"] for a in s["fbi"]["agencies"] for y in a["years"]]
    cst = s["crashes"]["stats"]
    cyears = [r["year"] for r in cst]
    return {
        "fbi_first": min(years), "fbi_last": max(years),
        "crash_first": min(cyears), "crash_last": max(cyears),
        "n_crashes": num(sum(r["crashes"] for r in cst)),
        "n_incidents": num(len(s["incidents"])),
        "first_incident_year": min(int(i["d"][:4]) for i in s["incidents"]),
        "n_timeline": num(len(D["history"]["timeline"])),
        "first_year": min(int(str(t["year"])[:4]) for t in D["history"]["timeline"] if str(t["year"])[:4].isdigit()),
        "n_people": num(len(D["history"]["people"])),
        "n_eat": num(len(D["civic"]["food_and_culture"])),
        "n_places": num(D["meta"]["stats"]["places"]),
        "n_streets": num(D["meta"]["stats"]["streets"]),
        "road_km": num(D["meta"]["stats"]["road_km"]),
        "this_year": D["today"].year,
    }


def _crime_dept(slug):
    t = TOWN_NAMES[slug]
    return Route(f"/crime/{slug}/", "crime-dept",
                 f"{t} crime, {{fbi_first}}–{{fbi_last}}: FBI figures explained" + BRAND,
                 f"Violent and property crime, cases cleared, arrests and staffing for the {t} Police Department, "
                 f"from its reports to the FBI.",
                 f"Crime in {t}, {{fbi_first}}–{{fbi_last}}", "I", "C", S_CRIME, ("safety",),
                 "pages_crime", "crime_dept", slug, "crime")


def _town(slug):
    t = TOWN_NAMES[slug]
    return Route(f"/towns/{slug}/", "town", f"{t}, Pa.: city hall, police, parks and figures" + BRAND,
                 f"City hall and police numbers, parks, neighborhoods, history, crime and crashes for {t}, Pa.",
                 f"{t}, Pa.: city hall, police, parks and figures", "I", "C", ("pubs", "pets", "app"), ALL_DATES,
                 "pages_towns", "town", slug, "towns")


SLUGS = ("new-kensington", "arnold", "lower-burrell")

ROUTES = [
    Route("/", "home", "NK15068: New Kensington, Arnold and Lower Burrell this week",
          "Lost and found pets, phone numbers, what's coming up and plain answers on crime for New Kensington, "
          "Arnold and Lower Burrell, Pa. (ZIP 15068).",
          "This week in 15068", "I", "-", S_HOME, ALL_DATES, "pages_home", "home", nav="home"),
    Route("/lost-pets/", "lost-pets", "Lost or found a pet in New Kensington, Arnold or Lower Burrell?" + BRAND,
          "Who to call first, the free 15068 lost and found board, and what to do in the first 48 hours. "
          "Animal Protectors: 724-339-7388.",
          "Lost or found a pet in 15068?", "I", "-", ("pubs", "nkmap", "pets", "app"), ("pets",),
          "pages_pets", "lost_pets", nav="lost-pets"),
    Route("/lost-pets/post/", "lost-pets-post", "Post a lost or found pet" + BRAND,
          "Fill in your pet's details once, then post them, share them or print a flyer.",
          "Post a lost or found pet", "N", "-", ("pubs", "pets", "app"), ("pets",),
          "pages_pets", "lost_pets_post", nav="lost-pets"),
    Route("/lost-pets/flyer/", "lost-pets-flyer", "Lost pet flyer" + BRAND,
          "A printable flyer for a lost or found pet in 15068.",
          "Lost pet flyer", "N", "-", ("pubs", "pets", "app"), ("pets",), "pages_pets", "flyer", nav="lost-pets"),
    Route("/numbers/", "numbers", "Phone numbers for New Kensington, Arnold and Lower Burrell" + BRAND,
          "Police non-emergency lines, city halls, the library, schools and animal help for ZIP 15068. "
          "Tap a number to call.",
          "Phone numbers for New Kensington, Arnold and Lower Burrell", "I", "-", S_BASIC, ("civic", "pets", "safety"),
          "pages_home", "numbers", nav="numbers"),
    Route("/calendar/", "calendar", "Coming up in New Kensington, Arnold and Lower Burrell" + BRAND,
          "Fridays on Fifth, council meetings, deadlines and yearly events in ZIP 15068, sorted by next date.",
          "Coming up in 15068", "I", "-", S_BASIC, ("civic", "history"), "pages_home", "calendar", nav="calendar"),
    Route("/crime/", "crime",
          "Crime in New Kensington, Arnold and Lower Burrell, {fbi_first}–{fbi_last}" + BRAND,
          "Is crime going up? Plain answers from each police department's FBI reports, the local police blotter "
          "and serious crashes.",
          "Is crime going up in New Kensington, Arnold and Lower Burrell?", "I", "C", S_CRIME, ("safety",),
          "pages_crime", "crime_hub", nav="crime"),
    *[_crime_dept(s) for s in SLUGS],
    Route("/crime/blotter/", "blotter", "Police blotter: news-reported incidents in 15068" + BRAND,
          "{n_incidents} incidents local news reported in New Kensington, Arnold and Lower Burrell since "
          "{first_incident_year}, placed on the block, with a link to each report.",
          "Police blotter: incidents reported in the news", "I", "-", ("pubs", "nkmap", "safety", "app"), ("safety",),
          "pages_crime", "blotter", nav="crime"),
    Route("/crashes/", "crashes", "Serious and fatal crashes in 15068, {crash_first}–{crash_last}" + BRAND,
          "{n_crashes} crashes that killed or seriously injured someone in New Kensington, Arnold and Lower Burrell, "
          "by town, year and road, from PennDOT records.",
          "Serious and fatal crashes in 15068, {crash_first}–{crash_last}", "I", "C", S_CRIME, ("safety",),
          "pages_crime", "crashes", nav="crime"),
    Route("/towns/", "towns", "New Kensington, Arnold and Lower Burrell: three cities, one ZIP" + BRAND,
          "Where each city is, how they differ, and each one's city hall and police numbers.",
          "Three cities share one ZIP code", "I", "-", S_BASIC, ("meta", "civic", "history", "safety"),
          "pages_towns", "towns_hub", nav="towns"),
    *[_town(s) for s in SLUGS],
    Route("/news/", "news", "Local news briefs from New Kensington, Arnold and Lower Burrell" + BRAND,
          "Short summaries of other outlets' reporting on the three cities, newest first, each linked to the original.",
          "Local news from the three cities", "I", "-", S_BASIC, ("civic",), "pages_towns", "news", nav="news"),
    Route("/history/", "history",
          "A history of New Kensington, Arnold and Lower Burrell, {first_year}–{this_year}" + BRAND,
          "{n_timeline} dated events from the Parnassus land tract to the Fifth Avenue revival, with neighborhoods, "
          "landmarks and sources.",
          "A history of 15068, from the {first_year} Parnassus tract to {this_year}", "I", "C", S_BASIC, ("history",),
          "pages_towns", "history", nav="history"),
    Route("/history/people/", "people", "Notable people from New Kensington, Arnold and Lower Burrell" + BRAND,
          "{n_people} people born or raised in ZIP 15068, from the inventor of Kevlar to NFL players, each sourced.",
          "Notable people from 15068", "I", "-", S_BASIC, ("history",), "pages_towns", "people", nav="history"),
    Route("/eat/", "eat", "Where to eat and drink in New Kensington, Arnold and Lower Burrell" + BRAND,
          "{n_eat} restaurants, bars, bakeries and clubs in ZIP 15068 with a published write-up.",
          "Where to eat and drink in 15068", "I", "-", S_BASIC, ("civic", "meta"), "pages_towns", "eat", nav="eat"),
    Route("/map/", "map", "Map of ZIP 15068: New Kensington, Arnold and Lower Burrell" + BRAND,
          "Search {n_places} places and {n_streets} streets on a map drawn from open data, with lost pets, police "
          "incidents and serious crashes.",
          "Map of ZIP 15068", "I", "-", ("pubs", "nkmap", "safety", "pets", "search", "app"), ("meta", "safety"),
          "pages_map", "map_page", nav="map"),
    Route("/map/3d/", "map3d", "15068 in 3D" + BRAND,
          "The ZIP's hills, river and buildings in 3D, drawn from open elevation and map data.",
          "15068 in 3D", "N", "-", ("three", "pubs", "nkmap", "nk3d", "app"), ("meta",), "pages_map", "map3d", nav="map"),
    Route("/poster/", "poster", "The 15068 map poster" + BRAND,
          "Every road in ZIP 15068 drawn from open data. Download it free to print at any size.",
          "The 15068 map poster", "I", "-", ("pubs", "nkmap", "app"), ("meta",), "pages_towns", "poster", nav="more"),
    Route("/directory/", "directory", "Places and streets A to Z" + BRAND,
          "Every place and street in the NK15068 map data, A to Z, with phone numbers and map links.",
          "Places and streets A to Z", "NF", "-", ("pubs", "nkmap", "app"), ("meta",), "pages_map", "directory",
          nav="more"),
    Route("/search/", "search", "Search NK15068",
          "Search places, streets, phone numbers, events and lost pets in 15068.",
          "Search 15068", "N", "-", ("pubs", "pets", "search", "app"), ALL_DATES, "pages_map", "search_page",
          nav="more"),
    Route("/whats-new/", "whats-new", "What's new on NK15068",
          "Every data update to NK15068, newest first: new news briefs, incidents, FBI years and map releases.",
          "What's new on NK15068", "I", "-", S_BASIC, ("changelog",), "pages_towns", "whats_new", nav="more"),
    Route("/about/", "about", "About NK15068",
          "Who runs NK15068, what it is, how it's made and kept up to date, and how to report a correction.",
          "About NK15068", "I", "-", S_BASIC, ("meta", "civic", "history"), "pages_towns", "about", nav="more"),
    Route("/privacy/", "privacy", "Privacy policy" + BRAND,
          "What NK15068 stores on your device, what it sends where, and how ads and cookies work on the site.",
          "Privacy policy", "I", "-", S_BASIC, (), "pages_towns", "privacy", nav="more"),
    Route("/contact/", "contact", "Contact and corrections" + BRAND,
          "How to reach NK15068 and report a correction to anything on the site.",
          "Contact and corrections", "I", "-", S_BASIC, (), "pages_towns", "contact", nav="more"),
    Route("/sources/", "sources", "Sources and licenses" + BRAND,
          "Every dataset and outlet NK15068 draws on, with licenses and compile dates.",
          "Sources and licenses", "I", "-", S_BASIC, ALL_DATES, "pages_towns", "sources", nav="more"),
    Route("/404.html", "not-found", "Page not found" + BRAND, "", "That page isn't here", "N", "-", S_BASIC, (),
          "pages_towns", "not_found"),
]

AD_ROUTES = [r.path for r in ROUTES if r.ads == "C"]
assert len(AD_ROUTES) == 9, AD_ROUTES


def resolve(D):
    """ROUTES with {placeholders} filled from the data."""
    f = facts(D)
    return [replace(r, title=r.title.format(**f), desc=r.desc.format(**f), h1=r.h1.format(**f)) for r in ROUTES]


def by_path(routes, path):
    return next(r for r in routes if r.path == path)


def dynamic(path, page, title, desc, h1, index="N", scripts=S_HOME, dates=("pets",), nav=None):
    """A route made at build time (the per-listing pet pages)."""
    return Route(path, page, title, desc, h1, index, "-", scripts, dates, "", "", nav=nav)
