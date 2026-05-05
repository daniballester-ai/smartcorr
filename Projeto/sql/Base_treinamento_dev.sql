
    SELECT  
        [date] [DATA]
        ,[CodeLevelServiceStructure3]
        ,[ScheduledWorktime]
        ,[FpwIdHierarchyLevel1] 
        ,IIF(convert(date,getdate()) >= date,[LackOfWorkday],0) [LackOfWorkday]
        ,[JustifiedEventFlag]
        ,[hiredmonths]
        ,ISNULL(B.Latitude,0) [latExp]
        ,ISNULL(B.Longitude,0) [longExp]
        ,ISNULL(C.Latitude,0) [latSite]
        ,ISNULL(C.Longitude,0) [longSite]
    FROM [dbAbs].[dbo].[factMicroGestao2] A
    LEFT JOIN [dbo].[CEPS] B  ON A.ZipCode=B.ZipCode
    LEFT JOIN [dbo].[CEPS] C  ON A.[CapacityCep]=C.ZipCode
    WHERE [date] BETWEEN '{{data_inicial}}' AND '{{data_final}}'

    AND CodeLevelServiceStructure3 IN (
  SELECT [CodeLevelServiceStructure3] FROM  ( 
    SELECT TOP 10 [CodeLevelServiceStructure3],MAX(InsertDateCtrl)InsertDateCtrl FROM [dbo].[ProcessoAbsenteismoPredicao] WITH (NOLOCK) 
 WHERE [data] BETWEEN '{{data_inicial}}' AND '{{data_final}}'
 GROUP BY [CodeLevelServiceStructure3]
 ORDER BY 2 ASC) AS CodeClient
  
--  WHERE  CAST(insertDateCtrl AS Date) <> CAST(GETDATE() AS Date)
  )   