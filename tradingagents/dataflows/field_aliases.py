"""Every source's spelling of the Company page's fields, in one table.

The field names are the ones ``company_profile.CompanyData`` documents (sales,
total_expenses, interest, depreciation, pbt, tax, net_profit, eps, share_capital,
equity, total_debt, ...). Each source maps its own labels onto them here, so a
figure means the same thing whichever source filled it, and a new spelling is a
new row rather than a change at a call site.

Within a field's alternatives the first one present wins; a tuple of names sums
those present. Values are never added across alternatives, which would count a
figure twice when a source reports it under two names.

``yahoo``  yfinance statement labels and ``Ticker.info`` keys.
``xbrl``   NSE/BSE results filings, by element local name. One table serves all
           four formats, since they share most names: Ind-AS companies, banks,
           NBFCs, in the BSE ``in-bse-fin`` taxonomy (filings to December 2024)
           and SEBI's ``in-capmkt`` Integrated Filing (March 2025 on). A
           format's own spellings follow the common ones; ``XBRL_DERIVED``
           lists the fields worked out in code instead (``india.xbrl``).
``shareholding``  shareholding-pattern filings (``in-bse-shp``), by member of
           ``CategoryOfShareholdersAxis``.
"""

from __future__ import annotations

ALIASES = {
    "yahoo": {
        "quote": {  # Ticker.info keys
            "name": ("longName", "shortName"),
            "exchange": ("fullExchangeName", "exchange"),
            "sector": ("sector",),
            "industry": ("industry",),
            "website": ("website",),
            "summary": ("longBusinessSummary",),
            "currency": ("currency",),
            "financial_currency": ("financialCurrency",),
            "quote_type": ("quoteType",),
            "price": ("currentPrice", "regularMarketPrice"),
            "previous_close": ("regularMarketPreviousClose", "previousClose"),
            "change": ("regularMarketChange",),
            "change_pct": ("regularMarketChangePercent",),
            "market_cap": ("marketCap",),
            "high_52w": ("fiftyTwoWeekHigh",),
            "low_52w": ("fiftyTwoWeekLow",),
            "pe": ("trailingPE",),
            "book_value": ("bookValue",),
            "dividend_yield": ("dividendYield",),  # in percent since yfinance 0.2.54
        },
        "income": {  # income_stmt and quarterly_income_stmt rows
            "sales": ("Total Revenue", "Operating Revenue"),
            "total_expenses": ("Total Expenses",),
            "operating_income": ("Operating Income", "Total Operating Income As Reported"),
            "cogs": ("Cost Of Revenue", "Reconciled Cost Of Revenue"),
            "interest": ("Interest Expense", "Interest Expense Non Operating"),
            "depreciation": ("Reconciled Depreciation", "Depreciation And Amortization In Income Statement",
                             "Depreciation Amortization Depletion Income Statement",
                             "Depreciation Income Statement"),
            "pbt": ("Pretax Income",),
            "tax": ("Tax Provision",),
            "net_profit": ("Net Income Including Noncontrolling Interests", "Net Income Continuous Operations",
                           "Net Income"),
            "net_income": ("Net Income Common Stockholders", "Net Income",
                           "Net Income From Continuing Operation Net Minority Interest"),
            "eps": ("Diluted EPS", "Basic EPS"),
            "interest_income": ("Interest Income", "Interest Income Non Operating"),
            "net_interest_income": ("Net Interest Income",),
        },
        "balance": {  # balance_sheet rows
            "share_capital": ("Common Stock", "Capital Stock"),
            "equity": ("Stockholders Equity", "Common Stock Equity"),
            "total_debt": ("Total Debt",),
            "lease_liabilities": ("Capital Lease Obligations",),
            "total_assets": ("Total Assets",),
            "current_assets": ("Current Assets",),
            "current_liabilities": ("Current Liabilities",),
            "net_ppe": ("Net PPE",),
            "cwip": ("Construction In Progress",),
            "intangibles": ("Goodwill And Other Intangible Assets", ("Goodwill", "Other Intangible Assets")),
            "investments": ("Investments And Advances", ("Long Term Equity Investment",
                            "Investmentin Financial Assets", "Investment Properties", "Other Investments")),
            "current_investments": ("Other Short Term Investments",),
            "receivables": ("Accounts Receivable", "Receivables"),
            "inventory": ("Inventory",),
            "payables": ("Accounts Payable", "Payables"),
            "shares": ("Ordinary Shares Number", "Share Issued"),
        },
        "cashflow": {  # cashflow rows
            "operating": ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
            "investing": ("Investing Cash Flow", "Cash Flow From Continuing Investing Activities"),
            "financing": ("Financing Cash Flow", "Cash Flow From Continuing Financing Activities"),
            "free_cash_flow": ("Free Cash Flow",),
        },
    },
    "xbrl": {
        # Duration facts: the quarter and the year to date of each results filing.
        "income": {
            "sales": ("RevenueFromOperations",),  # banks and NBFCs: see XBRL_DERIVED
            "other_income": ("OtherIncome",),
            "total_income": ("Income",),
            "cogs": (("CostOfMaterialsConsumed", "PurchasesOfStockInTrade",
                      "ChangesInInventoriesOfFinishedGoodsWorkInProgressAndStockInTrade"),),
            "employee_cost": ("EmployeeBenefitExpense", "EmployeesCost"),
            "interest": ("FinanceCosts", "InterestExpended"),
            "depreciation": ("DepreciationDepletionAndAmortisationExpense",),
            "other_expenses": ("OtherExpenses",),
            "exceptional_items": ("ExceptionalItemsBeforeTax", "ExceptionalItems"),
            "pbt": ("ProfitBeforeTax", "ProfitLossFromOrdinaryActivitiesBeforeTax"),
            "tax": ("TaxExpense",),
            "net_profit": ("ProfitLossForPeriod", "ProfitLossForThePeriod"),
            "net_income": ("ProfitOrLossAttributableToOwnersOfParent",
                           "ProfitLossAfterTaxesMinorityInterestAndShareOfProfitLossOfAssociates"),
            "minority_interest": ("ProfitOrLossAttributableToNonControllingInterests",
                                  "ProfitLossOfMinorityInterest"),
            "eps": ("DilutedEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                    "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                    "DilutedEarningsPerShareAfterExtraordinaryItems",
                    "BasicEarningsPerShareAfterExtraordinaryItems"),
            "eps_basic": ("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations",
                          "BasicEarningsPerShareAfterExtraordinaryItems"),
            "paid_up_capital": ("PaidUpValueOfEquityShareCapital",),
            "face_value": ("FaceValueOfEquityShareCapital",),
            "reserves_ex_revaluation": ("ReserveExcludingRevaluationReserves",),
            # Banks and NBFCs
            "interest_income": ("InterestEarned",),
            "operating_expenses": ("OperatingExpenses",),
            "operating_profit_before_provisions": ("OperatingProfitBeforeProvisionAndContingencies",),
            "provisions": ("ProvisionsOtherThanTaxAndContingencies", "ImpairmentOnFinancialInstruments"),
            "fee_income": ("FeesAndCommissionIncome",),
            "gross_npa": ("GrossNonPerformingAssets",),
            "net_npa": ("NonPerformingAssets",),
            "gross_npa_ratio": ("PercentageOfGrossNpa",),  # a fraction: 0.0117 is 1.17%
            "net_npa_ratio": ("PercentageOfNpa",),
            "cet1_ratio": ("CET1Ratio",),
            "return_on_assets": ("ReturnOnAssets",),
        },
        # Instant facts: the statement of assets and liabilities, filed with the
        # second- and fourth-quarter results.
        "balance": {
            "share_capital": ("EquityShareCapital", "Capital"),
            "other_equity": ("OtherEquity", "ReservesAndSurplus"),
            "equity": ("EquityAttributableToOwnersOfParent", "Equity", ("Capital", "ReservesAndSurplus")),
            "minority_equity": ("NonControllingInterest",),
            "total_debt": (("BorrowingsNoncurrent", "BorrowingsCurrent", "DebtSecurities", "Borrowings",
                            "SubordinatedLiabilities"),),
            "deposits": ("Deposits",),
            "total_assets": ("Assets",),
            "current_assets": ("CurrentAssets",),
            "current_liabilities": ("CurrentLiabilities",),
            # Phase 1's net PPE includes capital work in progress, which fixed
            # assets then take out again; intangibles under development count as CWIP.
            "net_ppe": (("PropertyPlantAndEquipment", "CapitalWorkInProgress",
                         "IntangibleAssetsUnderDevelopment", "InvestmentProperty"), "FixedAssets"),
            "cwip": (("CapitalWorkInProgress", "IntangibleAssetsUnderDevelopment"),),
            "intangibles": (("Goodwill", "OtherIntangibleAssets"),),
            "investments": (("NoncurrentInvestments", "InvestmentsAccountedForUsingEquityMethod"),
                            "Investments"),
            "current_investments": ("CurrentInvestments",),
            "receivables": (("TradeReceivablesCurrent", "TradeReceivablesNoncurrent"), "TradeReceivables"),
            "inventory": ("Inventories",),
            "payables": (("TradePayablesCurrent", "TradePayablesNoncurrent"),),
            "cash": ("CashAndCashEquivalents", ("CashAndBalancesWithReserveBankOfIndia",
                     "BalancesWithBanksAndMoneyAtCallAndShortNotice")),
            "advances": ("Advances", "Loans"),
        },
        # Duration facts of the cash flow statement: the year (or half year) to date.
        "cashflow": {
            "operating": ("CashFlowsFromUsedInOperatingActivities",),
            "investing": ("CashFlowsFromUsedInInvestingActivities",),
            "financing": ("CashFlowsFromUsedInFinancingActivities",),
            "capex": (("PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
                       "PurchaseOfTangibleAssetsClassifiedAsInvestingActivities",
                       "PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities",
                       "PurchaseOfIntangibleAssetsUnderDevelopment"),),
            "dividends_paid": ("DividendsPaidClassifiedAsFinancingActivities",),
        },
    },
    "shareholding": {
        # Category percentages; a list of members is summed, and DII in the
        # pre-2022 format is institutions less the foreign ones (XBRL_DERIVED).
        "promoter_pct": ("ShareholdingOfPromoterAndPromoterGroupMember",),
        "fii_pct": ("InstitutionsForeignMember",
                    ("InstitutionsForeignPortfolioInvestorMember", "ForeignVentureCapitalInvestorsMember",
                     "ForeignInstitutionsMember")),
        "dii_pct": ("InstitutionsDomesticMember",),
        "govt_pct": ("GovernmentsMember", "GovermentsMember",  # sic, the 2020 taxonomy
                     "CentralGovernmentOrStateGovernmentSOrPresidentOfIndiaMember"),
        "public_pct": ("NonInstitutionsMember",),
        "others_pct": ("SharesHeldByNonPromoterNonPublicShareholdersMember",),
        "total": ("ShareholdingPatternMember",),
    },
}

# Fields the XBRL table cannot express as a first-present or a sum, worked out in
# ``india.xbrl`` from the fields above. Listed here so the table stays the one
# place that says where every field comes from.
XBRL_DERIVED = {
    "total_expenses": "Expenses minus FinanceCosts: Phase 1's meaning, operating costs with "
                      "depreciation and without interest (Ind-AS 'Expenses' includes both)",
    "sales (banks)": "Income minus InterestExpended: net interest income plus other income",
    "sales (NBFCs)": "Income minus FinanceCosts",
    "net_interest_income": "InterestEarned minus InterestExpended (banks) or FinanceCosts (NBFCs)",
    "net_income": "net_profit when the filing has no attributable-to-owners line (standalone)",
    "free_cash_flow": "operating minus capex",
    "dii_pct (pre-2022)": "InstitutionsMember minus the foreign institutions",
    "pledged_pct": "promoter shares pledged, as a % of promoter shares (2025 format: pledges "
                   "only; earlier formats: pledged or otherwise encumbered)",
}

# Numeric elements a results filing reports that no field reads, on purpose: the
# subtotals and breakdowns behind the fields above, as seen in RELIANCE, HDFCBANK
# and BAJFINANCE filings of each format. A numeric element outside the table,
# this set and the families below is counted as unknown, so a new spelling shows
# up in `tradingagents india status` instead of silently going missing.
XBRL_UNUSED = frozenset({
    # Ind-AS profit and loss
    "Expenses", "ProfitBeforeExceptionalItemsAndTax", "CurrentTax", "DeferredTax",
    "NetMovementInRegulatoryDeferralAccountBalancesRelatedToProfitOrLossAndTheRelatedDeferredTaxMovement",
    "ProfitLossForPeriodFromContinuingOperations", "ProfitLossFromDiscontinuedOperationsBeforeTax",
    "TaxExpenseOfDiscontinuedOperations", "ProfitLossFromDiscontinuedOperationsAfterTax",
    "ShareOfProfitLossOfAssociatesAndJointVenturesAccountedForUsingEquityMethod",
    "OtherComprehensiveIncomeNetOfTaxes", "ComprehensiveIncomeForThePeriod", "OtherComprehensiveIncome",
    "ComprehensiveIncomeForThePeriodAttributableToOwnersOfParent",
    "ComprehensiveIncomeForThePeriodAttributableToOwnersOfParentNonControllingInterests",
    "BasicEarningsLossPerShareFromContinuingOperations", "DilutedEarningsLossPerShareFromContinuingOperations",
    "BasicEarningsLossPerShareFromDiscontinuedOperations", "DilutedEarningsLossPerShareFromDiscontinuedOperations",
    "DebtEquityRatio", "DebtServiceCoverageRatio", "InterestServiceCoverageRatio",
    "AmountOfItemThatWillNotBeReclassifiedToProfitAndLoss", "AmountOfItemThatWillBeReclassifiedToProfitAndLoss",
    "IncomeTaxRelatingToItemsThatWillNotBeReclassifiedToProfitOrLoss",
    "IncomeTaxRelatingToItemsThatWillBeReclassifiedToProfitOrLoss",
    "IncomeTaxRelatingToItmesThatWillNotBeReclassifiedToProfitOrLoss",  # sic, in-bse-fin 2020
    "IncomeTaxRelatingToItmesThatWillBeReclassifiedToProfitOrLoss",
    # Ind-AS assets and liabilities
    "BiologicalAssetsOtherThanBearerPlants", "LoansNoncurrent", "OtherNoncurrentFinancialAssets",
    "NoncurrentFinancialAssets", "DeferredTaxAssetsNet", "OtherNoncurrentAssets", "NoncurrentAssets",
    "BankBalanceOtherThanCashAndCashEquivalents", "LoansCurrent", "OtherCurrentFinancialAssets",
    "CurrentFinancialAssets", "CurrentTaxAssets", "OtherCurrentAssets", "NoncurrentAssetsClassifiedAsHeldForSale",
    "RegulatoryDeferralAccountDebitBalancesAndRelatedDeferredTaxAssets",
    "TotalOutstandingDuesOfMicroEnterpriseAndSmallEnterpriseNoncurrent",
    "TotalOutstandingDuesOfCreditorsOtherThanMicroEnterpriseAndSmallEnterpriseNoncurrent",
    "OtherNoncurrentFinancialLiabilities", "NoncurrentFinancialLiabilities", "ProvisionsNoncurrent",
    "DeferredTaxLiabilitiesNet", "DeferredGovernmentGrantsNoncurrent", "OtherNoncurrentLiabilities",
    "NoncurrentLiabilities", "TotalOutstandingDuesOfMicroEnterpriseAndSmallEnterpriseCurrent",
    "TotalOutstandingDuesOfCreditorsOtherThanMicroEnterpriseAndSmallEnterpriseCurrent",
    "OtherCurrentFinancialLiabilities", "CurrentFinancialLiabilities", "OtherCurrentLiabilities",
    "ProvisionsCurrent", "CurrentTaxLiabilities", "DeferredGovernmentGrantsCurrent",
    "LiabilitiesDirectlyAssociatedWithAssetsInDisposalGroupClassifiedAsHeldForSale",
    "RegulatoryDeferralAccountCreditBalancesAndRelatedDeferredTaxLiability", "Liabilities",
    "EquityAndLiabilities", "CashAndCashEquivalentsCashFlowStatement",
    # Banks
    "InterestOrDiscountOnAdvancesOrBills", "RevenueOnInvestments",
    "InterestOnBalancesWithReserveBankOfIndiaAndOtherInterBankFunds", "OtherInterest",
    "OtherOperatingExpenses", "ExpenditureExcludingProvisionsAndContingencies",
    "ProfitLossFromOrdinaryActivitiesAfterTax", "ExtraordinaryItems", "ShareOfProfitLossOfAssociates",
    "PercentageOfShareHeldByGovernmentOfIndia", "AdditionalTier1Ratio",
    "BasicEarningsPerShareBeforeExtraordinaryItems", "DilutedEarningsPerShareBeforeExtraordinaryItems",
    "OtherLiabilitiesAndProvisions", "CapitalAndLiabilities", "OtherAssets",
    "ProfitBeforeExtraordinaryItemsAndTax",
    # NBFCs
    "DividendIncome", "RentalIncome", "NetGainOnFairValueChanges",
    "NetGainOnDerecognitionOfFinancialInstrumentsUnderAmortisedCostCategory", "RevenueFromSaleOfProduct",
    "RevenueFromSaleOfServices", "OtherRevenueFromOperations", "FeesAndCommissionExpense",
    "NetLossOnFairValueChanges", "NetLossOnDerecognitionOfFinancialInstrumentsUnderAmortisedCostCategory",
    "DerivativeFinancialInstrumentsFinancialAssets", "OtherFinancialAssets", "FinanicalAssets",  # sic
    "FinancialAssets", "CurrentTaxAssetsNet", "OtherNonFinancialAssets", "NonFinancialAssets",
    "DerivativeFinancialInstrumentsFinancialLiabilities",
    "TotalOutstandingDuesOfMicroEnterpriseAndSmallEnterprise",
    "TotalOutstandingDuesOfCreditorsOtherThanMicroEnterpriseAndSmallEnterprise",
    "TotalOutstandingDuesOfMicroEnterpriseAndSmallEnterpriseOtherPayables",
    "TotalOutstandingDuesOfCreditorsOtherThanMicroEnterpriseAndSmallEnterpriseOtherPayables",
    "OtherFinancialLiabilities", "FinancialLiabilities", "Provisions", "OtherNonFinancialLiabilities",
    "NonFinancialLiabilities",
    # Cash flow subtotals
    "CashFlowsFromUsedInOperations", "IncreaseDecreaseInCashAndCashEquivalentsBeforeEffectOfExchangeRateChanges",
    "EffectOfExchangeRateChangesOnCashAndCashEquivalents", "IncreaseDecreaseInCashAndCashEquivalents",
    "CashFlowsFromUsedInOperatingActivitiesBeforeExtraordinaryItems",
    "CashFlowsFromUsedInInvestingActivitiesBeforeExtraordinaryItems",
    "CashFlowsFromUsedInFinancingActivitiesBeforeExtraordinaryItems",
    "ProceedsFromIssuingShares", "ProceedsFromIssuingOtherEquityInstruments",
    "ProceedsFromIssuingDebenturesNotesBondsEtc", "ProceedsFromExerciseOfStockOptions",
    "ProceedsFromChangesInOwnershipInterestsInSubsidiaries", "PaymentsFromChangesInOwnershipInterestsInSubsidiaries",
    "PaymentsToAcquireOrRedeemEntitysShares", "PaymentsOfOtherEquityInstruments",
    "ProceedsFromGovernmentGrantsClassifiedAsInvestingActivities",
    "CashReceiptsFromShareOfProfitsOfPartnershipFirmOrAssociationOfPersonsOrLimitedLiabilityPartnerships",
    "CashPaymentForInvestmentInPartnershipFirmOrAssociationOfPersonsOrLimitedLiabilityPartnerships",
    "ShareOfProfitAndLossFromPartnershipFirmOrAssociationOfPersonsOrLimitedLiabilityPartnerships",
})
# Families of detail no field reads: segment reporting, the operating cash flow
# reconciliation, and the cash flow statement's line items.
XBRL_UNUSED_PREFIXES = ("Segment", "InterSegment", "UnAllocable", "NetSegment", "OtherUnallocable",
                        "Adjustments", "OtherAdjustments")
XBRL_UNUSED_INFIXES = ("ClassifiedAs",)
