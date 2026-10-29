# Feedbacks

Feedbacks came from the real employee that must be in the app.

## General

- Multiple laptop usage via one database or sync feature or a way to handle... Probably need to migrate postresql.

## Products tab

- "düzenle" edit button must also modify quantity of the products which current another button make it redundant.
- CSV export feature
- Select more than one product to be able to increase productivity. With this approach employee can archive more fastly.
- Add delete button to delete from database for clear database but ask confirm it for deletions.
- Not-mvp but good to insert a update button to scrap arcelik.com.tr for latest products prices. I already have a scrapping python script, just need to use that script code to add it this app or I can add it as a package. That script is work as expected, it is currently able to parsed all the necessary products. Now I also going to add that script to be able to parse only the whitelist and blocklist other non needed to improve performance, and decrease the 404 errors. I never saw any error on first parse though... Anyway, this need a precise research and information to not get banned because if company ip get banned, we are fucked. I though, simple solution can be restriction for employee to update it only when the prices changes. We can give it like 5 time in one month etc. I could figure it out how much time prices changes etc.
- Product quantity calculation is probably need to be have more like fiziksel stok, fiziksel rezerve miktar, kullanılabilir miktar.

## Calculator Tab

- POS calculation need to be divided according to products prices. For example, most of the time some products value higher than the small one, so we need to decrease lower on small and more on higher like %70 %30 example.(This is example, open the suggestions.)
- Writing every product line by line is decrease productivity which we must insert boss input for every product line but boss mostly give it for total not per products. So, line by line handling useless. Most important is the POS inserting value and how much we are going to divide per product. If there is one product than thats normal to use line but we must use the total calculator.
- We must divide the POS inserting per product while be able to use total. I think that we don't use line line inserting instead we need a section to insert the products fastly with the current search and use a one total boss input section instead of line by line would solve the problem?
- We must show the total first price, website discounted price, total %10, total %15, total 18, total %20 but those need to be better readeable, we might show it like a dropdown hideable openable section etc. like a hint etc. Current only show "toplam indirim tutarı" which it isn't useful.
- Seems like current show the POS inserting per line because we write the boss input per line but employee want to write boss for full all lines but still want to divide POS entry input to the products correctly. Example total POS is 68.131 than it is going to be divide it to: one pos 33.304, another 34.826
- We need to improve this productivity to decrease manual interventions. For example, Percentage discount is must be auto detected by the script when there is decimal discounts.
- Satır toplam fiyat and birim fiyat seems do nothing if I am not wrong?
- Support fast calculation without inserting any products for only the POS find which some employee might use it only for the calculation without entering any product etc. which that's normal because we already insert all the products name to microsoft dynamics 365, so inserting this app make it redundant for employee.
  - I still think that there might be value in it and I want to keep it because we give a offer to customers, so that adding products have value for fast finding their first value and website discount. We just need to have a total bos inserting for all the inserted products, so myself can add products fastly which we already have search bar and than I can just enter total boss price and than see the all the website discount etc. for total. We must still add total first price, total discounted price and total boss price input for fast calculation but I still want to keep the product inserting but line by line handling stil rendundant, open suggestions for this... need brainstrom.
  - Other employe workflow is little differ, it want it to fast total calculation like even inserting total first price, total dsicounted prices and total boss price and just want to calculation without product selection.

## History tab

- Add history deletion with ask confirm popup.
- Add customer name for remember.

## Percentage discounts

- Calculation is work as expected but total calculation won't work. Why? because oddly, example; p1 and p2 has the Percentage discounte if we sell them different user or with different invoice but if we sell them together, Percentage discount isn't work, it uses another different offer. Anyway, I inserted percentage discount to website_discounted_price section for this two and when I add those to calculation, it give me 68.131.,1817342.. which correct algoritmh that work but POS isn't give this offer when this two going to be selled together. It goes back to website_discounted_price differently. Quick workaround is the change website saved discount when this two going to be in calculator but line by line handling is hard solution, above total handling might help while line by line also divided when we refactor total line ?? Also, any employe doesn't want to bother to customize the line by line products for every line, it just care the total and that the total divided POS entry per product but only display.
