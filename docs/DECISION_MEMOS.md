# Decision memos

Four one-page memos in plain English. They are written as if for a category buyer or a supply planner. The numbers come from American cold-cereal data from 2017 and from labelled assumptions; none of it is Sainsbury's data. Each memo ends with the test to run before anything changes.

## Memo 1. Which cereals to keep on a shelf that is 45% of the full range

**Decision.** Choose which of 274 selling cereals to range when the shelf can hold 45% of the full width, each sub-category keeps at least two products, and no supplier takes more than 35% of the shelf.

**Recommendation.** Range 123 products. The solver proves this is the best answer to the model (gap under 0.01%) in about half a second.

**Why.** A product earns its place by profit per unit of shelf width, but also by where its shoppers go when it is gone. If most of them would switch to a similar product that stays, dropping it costs little. The model keeps that in view; a simple ranking by profit per width does not.

**How much it matters.** On this catalogue the model beats the simple ranking by 0.7% of weekly profit if 60% of a dropped product's demand moves to a substitute, by 2.9% if 90% moves, and by 0.2% if only 30% moves. So the gain depends on a number the data cannot give us: how much demand really transfers. This number is assumed, not measured.

**Risks.** No effect of more space on sales; no cross-category effects; margins are assumed (28% brand, 38% own label).

**Before acting.** Run a store trial before any delisting: delist the 20 lowest-value products in test stores, match control stores on 26 weeks of sales, and measure the sales of the whole sub-category for 8 weeks. With 20 pairs the trial detects a 5% change 95% of the time and a 3% change 60% of the time. The number to read is the transfer rate.

## Memo 2. A 52-week promotion calendar for the top 40 cereals

**Decision.** Which of 40 cereals to put in the mailer or on display in which weeks, with six promotion slots a week, at most three of them displays, at least three weeks between promotions of the same product, and at most eight a year per product.

**Recommendation.** Use the calendar of 156 promotions, all of them displays. Modelled profit rises 4.4% over never promoting (the model assumes 18% of the price is funded on every promoted unit).

**Why.** In this data a display lifts sales far more than a mailer. A mailer's lift (about a third) does not cover an 18-point price funding on a 28% margin, so the model never chooses it; a display does. The ten best-selling products take 72 of the 156 displays and the ten smallest take none, and the spacing rule forces the calendar to rotate.

**What could be wrong.** The uplift is uncertain. Drawing it from its estimated range 1,000 times gives a gain between 176 and 250, almost always positive. That range covers only the noise in the uplift estimate. It does not cover the funding assumption or whether the uplift is the same for every product. In a simulated test where the true uplifts are known, planning on noisy estimates gave up between 3% and 29% of the best possible gain. Shading the estimates down made it worse, so I do not recommend that.

**Before acting.** Do not roll out all 156. Test the two largest assumptions first: run the display for 6 products in 20 matched store pairs, and read the uplift per product. Re-run the calendar with those estimates, which the command line does in under a second.

## Memo 3. How much to stock of a short-life line

**Decision.** Set the order-up-to level for 12 fast-selling lines with a three-day shelf life, a one-day delivery, and a shelf that holds a limited total.

**Recommendation.** It depends on the shelf. When the shelf is tight (70% of two days of demand), use the stochastic plan: it earned 9.5 more over 28 days (95% interval 5.7 to 13.3, about 1.4% of profit), with less waste (4.7% against 5.6%). When the shelf is not tight (115%), order up to mean demand: the stochastic plan was slightly worse (−4.4, interval −8.4 to −0.4). At 90% there is no detectable difference.

**Why.** A mean-demand plan holds as much of every line as it expects to sell. When space is plentiful that is nearly right. When space is short, the stochastic plan gives scarce space to the lines where an extra unit is most likely to sell, and holds back on the lines where it is likely to expire.

**Honesty note.** The demand shape and spread are real; that the line is short-life is an assumption, because cereal keeps. The fill rate is 73% to 80% in all plans, which reflects a one-day delivery and a three-day life, not a recommendation to accept it.

**Before acting.** Run the plan in shadow for four weeks on 10 stores: record the orders it would have made against actual sales and waste, then switch a matched half of the stores to it.

## Memo 4. When to mark down an overstocked lot

**Decision.** A lot holds twice the full-price demand for six weeks and loses 12% of its demand each week. How should it be priced?

**Recommendation.** Use one lower price from the start (about 40% below the usual price for these lots) rather than waiting and then cutting hard. On the 20 largest real cereals with this assumed overstock, the best price path earns 3.4% to 5.2% more revenue than holding the full price. The estimated price elasticity is 1.32 (interval 1.16 to 1.48).

**Why.** With elasticity above 1, cutting a price sells more units but earns less per unit, so the aim is to clear the stock at the highest price that clears it. A single price does that: because demand fades each week at the same rate for every price, the money earned from the last unit sold is equal in every week only when the price is the same in every week, so waiting does not help in this model.

**What could be wrong.** The elasticity comes from the shop's own price changes, not an experiment; promotions, seasonality and shoppers' stockpiling can make it look different from the true response. At an elasticity of 1.16 or 1.48 the best price moves, but the shape of the answer (one price) does not.

**Before acting.** Run a price test on 10 lots: half at the recommended price, half at the usual markdown, in matched stores, for the horizon. The test plan code gives the sample for the revenue measure.
