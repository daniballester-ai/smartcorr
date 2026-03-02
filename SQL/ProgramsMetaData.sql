SELECT TOP (15) 
       [program_ccmsid]
      ,[client_ccmsid]
      ,[client_legacyid]
      ,[client_cognosid]
      ,[client_enabled]
      ,[client_name]
      ,[client_friendly_name]
      ,[operationid]
      ,[operation_name]
      ,[operation_enabled]
      ,[program_legacyid]
      ,[program_location]
      ,[program_location_name]
      ,[program_name]
      ,[program_friendly_name]
      ,[program_dimension_ttv]
      ,[program_operational]
      ,[program_enabled]
      ,[lobtype]
      ,[lobtype_value]
      ,[channel]
      ,[channel_value]
      ,[channel_comp]
      ,[channel_comp_value]
      ,[industry]
      ,[industry_value]
      ,[businesstype]
      ,[businesstype_value]
      ,[billingtype]
      ,[billingtype_value]
      ,[lobid]
      ,[isdibs]
      ,[program_properties_editedby]
      ,[program_properties_editedon]
      ,[costcenter_cognosid]
      ,[costcenter_name]
      ,[costcenter_typecode]
      ,[costcenter_typename]
      ,[ttv_serverid]
      ,[ttv_servername]
      ,[ttv_ugid]
      ,[ttv_ugname]
      ,[site]
      ,[sitename]
      ,[siteuf]
      ,[crm_system]
      ,[crm_systemname]
      ,[operational_director]
      ,[program_default_language]
      ,[program_default_language_value]
      ,[fpw_poc_bimis]
      ,[fpw_poc_treinamento]
      ,[fpw_poc_wfm]
      ,[fpw_poc_qualidade]
      ,[program_external_poc_treinamento_name]
      ,[program_external_poc_treinamento_tel]
      ,[program_external_poc_treinamento_mail]
      ,[program_external_poc_wfm_name]
      ,[program_external_poc_wfm_tel]
      ,[program_external_poc_wfm_mail]
      ,[program_external_poc_qualidade_name]
      ,[program_external_poc_qualidade_tel]
      ,[program_external_poc_qualidade_mail]
      ,[program_external_poc_operacoes_name]
      ,[program_external_poc_operacoes_tel]
      ,[program_external_poc_operacoes_mail]
      ,[RowHash]
      ,[ValidFrom]
      ,[ValidTo]
      ,[operational_coo]
      ,[operational_quality_senior_manager]
      ,[program_secondary_language]
      ,[program_secondary_language_value]
      ,[program_compute_ttv_adh]
      ,[wfm_channel]
      ,[wfm_channel_value]
      ,[client_pct_cloud_negociation]
      ,[program_dimension_market]
      ,[program_dimension_market_value]
      ,[client_compensable_billing]
      ,[client_golife]
      ,[client_kickout]
      ,[client_pbi_path]
      ,[client_tplogin_name]
  FROM [DataCore].[Corp].[ProgramsMetaData] WITH(NOLOCK)
  WHERE operationid = 7076 
   --  AND channel = 7  -- Comentado para não excluir programas que não sejam do canal 7 (ex: Email, Voz)
    AND program_friendly_name IN (
        'Pagbank Bo Seguranca',
        'Pagbank Chat Meu Negocio',
        'Pagbank Chat Minha Conta',
        'Pagbank Chat Polos',
        'Pagbank Chat Seguranca',
        'Pagbank Email Varejo',
        'Pagbank Long Tail',
        'Pagbank Ouvidoria N1',
        'Pagbank Qualidade',
        'Pagbank Reclame Aqui',
        'Pagbank Redes Sociais Rn',
        'Pagbank Seguranca',
        'Pagbank Varejo',
        'Uol - Novo Pagbank Lt A.Valor',
        'Uol - Novo Pagbank Seg Desp'
    )