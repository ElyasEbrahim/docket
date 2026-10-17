"""Benchmark tasks on CFPB complaint narratives: label mapping, questions and experiment definitions.

Ground truth comes from the consumer-selected Product / Issue fields. Consumers sometimes pick the wrong product,
so agreement with these fields is a lower bound on the model's fidelity to the narrative.
"""
from dataclasses import dataclass, field

# Raw CFPB product names (all form revisions 2015–2024) → one stable label, written as a person would read it.
# Products that do not map cleanly ("Consumer Loan", "Prepaid card", "Other financial service",
# "Debt or credit management") are excluded from the sample.
PRODUCT_MAP = {
    "Credit reporting, credit repair services, or other personal consumer reports": "credit reporting",
    "Credit reporting or other personal consumer reports": "credit reporting",
    "Credit reporting": "credit reporting",
    "Debt collection": "debt collection",
    "Mortgage": "mortgage",
    "Credit card or prepaid card": "credit card",
    "Credit card": "credit card",
    "Checking or savings account": "checking or savings account",
    "Bank account or service": "checking or savings account",
    "Student loan": "student loan",
    "Money transfer, virtual currency, or money service": "money transfer or virtual currency",
    "Money transfers": "money transfer or virtual currency",
    "Virtual currency": "money transfer or virtual currency",
    "Vehicle loan or lease": "vehicle loan or lease",
    "Payday loan, title loan, or personal loan": "payday, title, or personal loan",
    "Payday loan, title loan, personal loan, or advance loan": "payday, title, or personal loan",
    "Payday loan": "payday, title, or personal loan",
}

PRODUCT_OPTIONS = [
    "credit reporting",
    "debt collection",
    "mortgage",
    "credit card",
    "checking or savings account",
    "student loan",
    "money transfer or virtual currency",
    "vehicle loan or lease",
    "payday, title, or personal loan",
]

PRODUCT_QUESTION = "Which financial product is this consumer complaint about?"

# Label-set drift: the most common real-world change is appending a catch-all option.
OTHER_OPTION = "other financial product or service"

INCORRECT_REPORT_ISSUES = {
    "Incorrect information on your report",
    "Incorrect information on credit report",
}


@dataclass(frozen=True)
class Experiment:
    name: str
    kind: str                      # 'noul' or 'choice'
    question: str
    options: tuple = ()            # ordered; empty for noul
    family: str = ""               # experiments in one family are compared with each other
    notes: str = ""

    @property
    def options_list(self):
        return list(self.options) if self.options else None


def rotate(options, k):
    k %= len(options)
    return list(options[k:]) + list(options[:k])


def default_experiments(shifts=(3, 6)):
    exps = [Experiment("choice_base", "choice", PRODUCT_QUESTION, tuple(PRODUCT_OPTIONS), "product",
                       "canonical option order")]
    for k in shifts:
        exps.append(Experiment(f"choice_shift{k}", "choice", PRODUCT_QUESTION,
                               tuple(rotate(PRODUCT_OPTIONS, k)), "product",
                               f"options cyclically shifted by {k}"))
    exps.append(Experiment("choice_other", "choice", PRODUCT_QUESTION,
                           tuple(PRODUCT_OPTIONS + [OTHER_OPTION]), "product",
                           "canonical order plus a catch-all option (label-set drift)"))
    exps.append(Experiment("noul_debt_collection", "noul",
                           "the complaint is about a debt collector or about collecting a debt",
                           family="debt_collection"))
    exps.append(Experiment("noul_incorrect_report", "noul",
                           "the consumer says their credit report contains incorrect information",
                           family="incorrect_report"))
    return exps


@dataclass
class Truth:
    """Ground truth for one complaint, derived from consumer-selected fields."""
    product: str
    issue: str
    extra: dict = field(default_factory=dict)


def noul_truth(experiment_family, truth):
    if experiment_family == "debt_collection":
        return truth.product == "debt collection"
    if experiment_family == "incorrect_report":
        return truth.issue in INCORRECT_REPORT_ISSUES
    raise KeyError(experiment_family)


def noul_family_for_condition(condition):
    """Map a noul condition text back to its task family (used by the simulated backend)."""
    for e in default_experiments():
        if e.kind == "noul" and e.question == condition:
            return e.family
    return None
