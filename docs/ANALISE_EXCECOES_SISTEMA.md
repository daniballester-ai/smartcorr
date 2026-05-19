# Análise das Variáveis de Exceção do Modelo

Este documento detalha como e através de quais fontes as novas variáveis (`SystemFailure`, `ClientSystemFailure` e `SeatUnavailable`) são montadas, além de mapear todos os filtros e regras aplicadas a elas na procedure `[OdsCorp].[dbo].[sp_LostAgentMinute_CRM]`.

## 1. Origens de Dados (Como as variáveis são montadas)

Na construção dessa procedure, essas três variáveis mensuram "exceções" ou desvios de tempo produtivo do atendente (mensuradas em horas decimais). Elas são formadas a partir das seguintes fontes:

*   **`SystemFailure` (System Failure)**: 
    Tem origem *mista*. É a soma do tempo apurado em duas bases:
    1. **Totem RH** (Tabela `AllowanceTime` do `TotemRH`): Soma dos eventos categorizados por subtipos 1, 2, 3, 4, 5 e 7 (que incluem falha sistêmica, queda de VPN, problemas no Citrix, travamento de computador e falha no ambiente de controle telefônico do consultor). 
    2. **WFM / Totalview** (Tabelas `AgentScheduleFullException` + `dimExceIEX`): Soma das exceções quando a dimensão do Totalview marca flag para problemas sistêmicos (`Presente_ProblemaSistema = 1`). Mapeada por trás do alias `[Technical Issues Time Adjustments]`.

*   **`ClientSystemFailure` (Client System Failure)**: 
    Vem **exclusivamente do WFM / Totalview**: 
    Soma do tempo nas marcações do Totalview onde a dimensão indica falha vinda do sistema do contratante/cliente (`Presente_ProblemasCliente = 1`).

*   **`SeatUnavailable` (Seat unavailable)**:
    Vem **exclusivamente do WFM / Totalview**: 
    Soma do tempo nas exceções do Totalview marcadas para quando o agente fica sem cadeira / impossibilitado de logar fisicamente (`Presente_IndisponibilidadeLugar = 1`).

## 2. Filtros e Regras Importantes Aplicados

### A. Filtro Restritivo por FlagWAHA (Home Office vs. Site)

Durante a aglutinação da base importada do WFM / Totalview (na `#ResultEscala`), existe o seguinte trecho:
```sql
WHERE FlagWAHA = 0 --VAI FICAR COM OS DADOS DE WFM APENAS PARA QUEM É BM, POIS TODOS DEVERIAM VIR PELO TOTEM RH E COMO AINDA NÃO ESTÁ 100% PARA BM CONTINUAMOS COLETANDO DO TTV
```
*   **O que isso significa na prática:** Como `SeatUnavailable` e `ClientSystemFailure` provém 100% de fontes do WFM, essas variáveis **estão zeradas para agentes remotos (WAHA)**. Elas só trarão valor real se o agente operar na modalidade de trabalho presencial (Site/Brick and Mortar).
*   Já a `SystemFailure` também desconsidera os dados do WFM para WAHA, mas **não ignora os dados do Totem RH**. Logo, o `SystemFailure` contabilizará os tempos tanto de WAHA quanto de Site, embora as exceções de Site sejam "engordadas" pelas pausas importadas pelo WFM. Para os registros que vêm do Totem RH, há apenas o filtro validando se a exceção já foi processada na folha (`BT.ProcessedTypeId BETWEEN 1 AND 4`).

### B. Ajuste Proporcional Baseado no Banco de Horas (Valor PPH)

No passo rotulado na procedure como geração da `#BASE_FINAL`, todas essas três variáveis sofrem um cálculo que cria um limitador (teto de horas):
*   Se a soma de todos os eventos registrados no dia do agente (Tempo Logado Principal + System Failure + Client System Failure + Seat Unavailable + Agent Issues, etc) for **maior** que a carga do "Ponto / Valor PPH" batida por ele, a procedure cria uma variável subtrativa matemática chamada de `Diferenca`.
*   A procedure usa essa diferença para aplicar um **desconto e rateio proporcional** em todas essas exceções, reduzindo o valor de todas elas até a soma delas caber ou se alinhar ao teto de tempo escalado do agente para o dia logado. Logo, caso um atendente tenha registrado uma falha muito extensa que estouraria sua carga de horário comparada ao expediente, esse limitador força um corte automático decrescendo as horas dessas 3 variáveis na tabela final.
