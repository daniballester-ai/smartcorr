 BEGIN
    SELECT
    a.date,
    a.CodeLevelServiceStructure3,
    a.ScheduledWorktime,
    a.FpwIdHierarchyLevel1,
    a.LackOfWorkday,
     a.JustifiedEventFlag,
     m.ZipCode,
     m.CapacityCep,
     DATEDIFF(MONTH,Hiredate,GETDATE()) hiredmonths
      FROM [OdsCorp].[DataMart].[factMicroGestao]  AS a with(nolock)
LEFT JOIN [OdsFpw].[dbo].[Employee] AS m with(nolock) ON A.FpwIdHierarchyLevel1 = m.fpwid and a.date between m.validFromCtrl and m.ValidToCtrl
     WHERE a.Date BETWEEN '{{data_inicial}}' AND '{{data_final}}'
END

