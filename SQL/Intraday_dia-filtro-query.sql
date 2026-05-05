SELECT TOP (1000) *
  FROM [OdsCorp].[DataMart].[factIntradayDelivery] WITH (NOLOCK)
  where program_ccmsid = 347851
    and RowDate = '2026-04-22'
    and Channel = 7
 order by rowdate desc, intervalo asc

/*-----------------------------------------------------------

-- Filtro para trazer apenas o retrato do dia atual em diante (Dashboard Vivo)
WHERE v.[DataRef] = '2026-04-22'

AND v.[CodPrograma] = 347851


/*
-- Filtro base da Operação Pagbank / Voz
AND v.[CodPrograma] IN (366845, 370587, 370588, 548619, 581345, 
          581346, 589266, 589360, 589361, 591529, 
          347851, 347858, 353059, 355491, 355492) 
*/
AND v.[Canal] = 7