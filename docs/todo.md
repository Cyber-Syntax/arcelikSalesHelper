# todo.md

## new scope

### Products tab

This tab will be used to keep warehouse products and their prices etc. It will be used to keep track of products count and their prices.

- [ ] Edit must be able to update quantity instead of new quantity button. Refactor it to use edit button for both quantity and price update. (Currently, edit button is only used for price update)
- [ ] if database different for products and database, it need to be same which more meaninful to have one database for products count and their prices. History database can be different.

### Calculator tab

This need to be able to used temporary or permanent calculators. Example, employee can calculate a product price quickly if the products not exist but after that line is new, product can be saveable from that tab to products database.

- [ ] Add save product and save history button to calculator tab. If the product is not exist, employee can save it to products database and also save the history of that calculation to history database both. If the product is exist, employee can save the history of that calculation to history database only or ask employee to override the product price etc. if there is difference on the current saved products which is more meaningful to have one database for products count and their prices. This isn't for a history database which we don't need to override that, history database is only for keeping history of calculations.
- [ ] Add option to sell products from calculator tab which we can have a options like offer/sell/openaccount(this also mean sell but customer will pay later) etc. Also we need to handle option for reservation of products which some customer bought the products with sell/openaccount option but they will pick it up after 1 month, 1 year later etc. and we offer only 13 months to keep reserve products in our warehouse. So, we also need a logic to notify employee if the product reservation is expired so employee can call the customer to let them know that their reservation is expired and they need to pick it up or we will sell it to another customer.
- [ ] add new feature pos price divide; for example if the POS give 100.000 most of the time first price would differe like one might 90.000, other 12.000 so we need to dive the 100.000 pos while we change products first price to match total 100.000, so we can give 89.500TL and 10.500TL would make 100.000 which we make divide the 2.000 according to prices. I wrote this an example, I assume that there is more better algorithm to divide those correctly. (it might more on big value, less on other...)

#### Calculator tab seems wrong

Examples how the calculation work, verified by real employee/customer and products:
first price: 145,298.00 (learned from the website/POS)
discounted price: 132,798.00 (learned from the website/POS)
Last/boss price: 112,000.00 (learned from the boss/manager)
discounted price %10: 119.518,20 (132.798,00 * 0,9)
POS: 124,500.00 (112,000,00 + 12,500,00)
discount: 12.500,00 (145,298.00 - 132,798.00)

Another example:
first price: 54,299.00 (learned from the website/POS)
discounted price: 48,299.00 (learned from the website/POS)
Last/boss price: 43,500.00 (learned from the boss/manager)
discounted price %10: 43,469.1 (48,299.00 * 0,9)
POS: 49,500.00 (43,500.00 + 6,000.00)
discount: 6,000.00 (54,299.00 - 48,299.00)

Another example with gift included:
first price: 53.199
discounted price: 45.199
boss gifted price: 48.000,00
boss discounted price: 38,000,00
POS gifted: 48.000,00 (POS system directly make 0 to gift price and write the 53.199, so POS system gifted is directly became the boss gifted price)
POS without gift: 46.000,00 (38.000,00 + 8.000,00)
discount amount: 8.000,00 TL
gift name: TKM 9961
gift price: 14.539
gift discounted price: 12.399

### History tab

History tab is used to keep track of the calculation done by employee to remember the previous offers to the customers, products prices etc. It is used to keep track of the previous calculations done by employee.

- [ ] Add optional customer name to keep track of the offers to the customers.

## must-have features

- [-] add a price for all of the products, not per line!!!
  - [ ] workoaround used now, first line can be useable for fast calculations
- [x] Verify all the calculation text which some seems unnecessary.
- [x] add turkish language support
- [ ] beautify the ui more responsive and user friendly
  - calculator and history need more better ui because currently there is a lot of written text and makes it hard to read and understand
- [ ] add csv export feature
- [ ] refactor business-helper constants to arcelikSalesHelper constants

## good-to-have features

- [ ] add excel export feature
- [ ] refactor product line add for fast calculation; for example, we might add multiple product in dropdown with multi select for fast product add.
