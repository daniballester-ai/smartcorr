SELECT	TOP 1  B.program_friendly_name
		, A.*
FROM [OdsCorp].[DataMart].factIntradayDelivery	A	WITH(NOLOCK) -- é uma view, por isso eu não achava
INNER JOIN [DataCore].[Corp].[ProgramsMetaData] B	WITH(NOLOCK)
   ON A.program_ccmsid = B.program_ccmsid
WHERE 1=1
  AND A.INTERVALO = '15:00:00'
  AND A.program_ccmsid = 347851
ORDER BY ROWDATE DESC 