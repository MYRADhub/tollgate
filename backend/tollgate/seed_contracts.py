"""Vendor contracts for the demo company, with the terms a reviewer approved."""

from __future__ import annotations

from datetime import date

CONTRACTS: dict[str, dict] = {
    "polaris": {
        "title": "Managed WAN Services Agreement",
        "effective": date(2025, 7, 1),
        "text": """MANAGED WAN SERVICES AGREEMENT

This Managed WAN Services Agreement is entered into as of July 1, 2025 between Polaris Network Services, Inc. ("Provider") and Halden Robotics, Inc. ("Customer").

1. Services. Provider shall supply and manage the dedicated MPLS circuits listed in Order Form 1, including the 1 Gbps circuit serving Customer's Salt Lake City plant (part MPLS-1G-SLC).

2. Charges. Customer shall pay the Monthly Recurring Charge stated in Order Form 1, invoiced monthly in advance. Payment terms are net thirty (30) days from the invoice date.

3. Monitoring. Availability is measured by Customer's network operations monitoring at one-minute intervals. Provider may dispute a measurement within ten (10) days of the end of the month by written notice with supporting logs.

4. Service Levels.
4.1 Provider commits to Monthly Availability of 99.95% for each circuit.
4.2 Service Credits. If Monthly Availability for a circuit falls below 99.95%, Provider shall credit Customer 10% of the Monthly Recurring Charge for that circuit; if it falls below 99.5%, 15%; and if it falls below 99.0%, 25%. Credits are applied against the next invoice issued after the month in which the shortfall occurred.
4.3 Service Credits are Customer's sole monetary remedy for unavailability, except as provided in Section 9.

5. Term. This Agreement continues for thirty-six (36) months from the effective date.
""",
        "terms": [
            {
                "kind": "sla_credit",
                "params": {"metric": "uptime_pct", "commitment_pct": 99.95, "skus": ["MPLS-1G-SLC"],
                           "tiers": [{"below_pct": 99.0, "credit_pct": 25}, {"below_pct": 99.5, "credit_pct": 15}, {"below_pct": 99.95, "credit_pct": 10}]},
                "quote": "If Monthly Availability for a circuit falls below 99.95%, Provider shall credit Customer 10% of the Monthly Recurring Charge for that circuit; if it falls below 99.5%, 15%; and if it falls below 99.0%, 25%.",
            }
        ],
    },
    "ostara": {
        "title": "Component Supply Agreement",
        "effective": date(2026, 2, 1),
        "text": """COMPONENT SUPPLY AGREEMENT

Between Ostara Components GmbH, Industriestrasse 14, Stuttgart ("Supplier") and Halden Robotics, Inc. ("Buyer"), effective February 1, 2026.

1. Products. Supplier shall sell to Buyer the motion-control components listed in Schedule A at the prices stated there, in US dollars.

2. Pricing.
2.1 Schedule A list prices apply to all orders unless this Section provides otherwise.
2.2 Volume Pricing. For orders of twenty (20) or more BLDC servo motors (part MTR-BLDC-48) on a single purchase order, the unit price shall be USD 1,121.00.
2.3 Prices are exclusive of sales tax and include delivery to Buyer's Salt Lake City facility.

3. Payment. Invoices are payable forty-five (45) days from the invoice date.

Schedule A: MTR-BLDC-48 BLDC servo motor 48V 750W, USD 1,180.00; ENC-14B 14-bit absolute encoder, USD 210.00.
""",
        "terms": [
            {
                "kind": "volume_price",
                "params": {"sku": "MTR-BLDC-48", "min_qty": 20, "unit_price": 1121.00},
                "quote": "For orders of twenty (20) or more BLDC servo motors (part MTR-BLDC-48) on a single purchase order, the unit price shall be USD 1,121.00.",
            }
        ],
    },
    "brightline": {
        "title": "Master Supply Agreement",
        "effective": date(2026, 1, 1),
        "text": """MASTER SUPPLY AGREEMENT

Brightline Industrial Supply ("Supplier") and Halden Robotics, Inc. ("Customer"), effective January 1, 2026.

4. Payment Terms. Invoices are due thirty (30) days from the invoice date. Customer may take a one percent (1%) discount on any invoice paid within ten (10) days of the invoice date.

5. Prices.
5.1 Prices for catalog items are set out in Schedule A.
5.3 Price Adjustments. Supplier may increase unit prices no more than once per calendar year and by no more than three percent (3%) over the prices in Schedule A.

Schedule A (USD per unit): BOLT-M8 44.00; GLOVE-L 12.50; GLS-SAFE 8.90; BRG-6204 4.10; LUBE-EP2 7.80.
""",
        "terms": [
            {
                "kind": "early_pay_discount",
                "params": {"discount_pct": 1, "within_days": 10},
                "quote": "Customer may take a one percent (1%) discount on any invoice paid within ten (10) days of the invoice date.",
            },
            {
                "kind": "price_cap",
                "params": {"base_prices": {"BOLT-M8": 44.00, "GLOVE-L": 12.50, "GLS-SAFE": 8.90, "BRG-6204": 4.10, "LUBE-EP2": 7.80}, "max_increase_pct": 3},
                "quote": "Supplier may increase unit prices no more than once per calendar year and by no more than three percent (3%) over the prices in Schedule A.",
            },
        ],
    },
    "granite": {
        "title": "Electrical Supply Agreement",
        "effective": date(2026, 3, 1),
        "text": """ELECTRICAL SUPPLY AGREEMENT

Granite Electrical Co. ("Seller") and Halden Robotics, Inc. ("Buyer"), effective March 1, 2026.

2. Pricing. Contract prices: CBL-12AWG 12 AWG THHN copper, 500 ft spool, USD 90.00; BRK-20A 20A single-pole breaker, USD 18.75. Seller may adjust contract prices for changes in commodity copper cost, provided that no contract price increases by more than five percent (5%) during the term.

3. Payment. Net thirty (30) days from the invoice date.
""",
        "terms": [
            {
                "kind": "price_cap",
                "params": {"base_prices": {"CBL-12AWG": 90.00, "BRK-20A": 18.75}, "max_increase_pct": 5},
                "quote": "Seller may adjust contract prices for changes in commodity copper cost, provided that no contract price increases by more than five percent (5%) during the term.",
            }
        ],
    },
    "lumen": {
        "title": "Office Supply Terms",
        "effective": date(2025, 11, 1),
        "text": """OFFICE SUPPLY TERMS OF SALE

Lumen Office Supply ("Lumen") and Halden Robotics, Inc. ("Customer").

1. Orders are placed through Customer's purchase order system.
2. Payment terms are net fifteen (15) days. Customer may deduct a two percent (2%) prompt-payment discount on any invoice paid within ten (10) days of the invoice date.
3. Prices are those in effect on the date of the purchase order.
""",
        "terms": [
            {
                "kind": "early_pay_discount",
                "params": {"discount_pct": 2, "within_days": 10},
                "quote": "Customer may deduct a two percent (2%) prompt-payment discount on any invoice paid within ten (10) days of the invoice date.",
            }
        ],
    },
    "vantage": {
        "title": "Enterprise Subscription Agreement",
        "effective": date(2025, 10, 1),
        "text": """ENTERPRISE SUBSCRIPTION AGREEMENT

Vantage Cloud Services ("Vantage") and Halden Robotics, Inc. ("Customer").

6. Fees and Payment. Subscription fees are invoiced quarterly in advance and are due thirty (30) days from the invoice date.
6.4 Remittance. Changes to Vantage's remittance instructions take effect only when made in writing on Vantage letterhead, signed by an officer of Vantage, and confirmed by Customer by telephone to Vantage's number of record.
""",
        "terms": [],
    },
}

# Our own network monitoring. Polaris had a fiber cut on October 14.
METRICS = [
    ("polaris", "2026-09", "uptime_pct", "99.982", "Halden NOC monitoring, 1-minute probes"),
    ("polaris", "2026-10", "uptime_pct", "99.310", "Halden NOC monitoring, 1-minute probes (fiber cut 14 Oct, 5h 08m outage)"),
]
