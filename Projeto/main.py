import os
import sys  
# descomentar as linhas 3 E 4 para por em produção
# enable_venv = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv','Scripts','activate_this.py')
# exec(open(enable_venv).read(), {'__file__': enable_venv})

venv_path = os.path.join(os.path.dirname(__file__), ".venv", "Lib", "site-packages") 


if venv_path not in sys.path:
    sys.path.insert(0, venv_path)

from argparse import ArgumentParser 
from AbsenteeismPredictor.main import AbsenteeismPredictor


def main():
    predictor = AbsenteeismPredictor(
        args.connectionString,
        args.dias_atras,
        args.dias_frente,
        args.ProcessTable,
        args.ProcessKey,
        args.FinalDateCtrl,
        args.dias_filtro_previsao
    )
    predictor.load_data_from_db()
    predictor.preprocess_data()
    predictor.feature_engineering()
    # Avaliação do modelo se solicitada
    evaluation_results = None
    if args.evaluate_model:
        predictor.display_data()
        evaluation_results = predictor.evaluate_overall_model(use_smote=False, plot_confusion_matrix=True)
    else:
        predictor.train_model_por_operacao(tune_hyperparams=False, use_smote=False)
        predictor.insert_data()
    
    
    return len(predictor.df_pred_insert) if predictor.df_pred_insert is not None else 0

if __name__ == "__main__":
    argParser = ArgumentParser('Corp - Projeto - abs preditivo')
    # para por em produção altere o required=False para required=True e comente as linhas que iniciam com default
    # para testes descomente as linhas 'default' abaixo.
    argParser.add_argument('--InitialDateCtrl',
                           help='Data Final de Proceso.',
                           required=True,
                            default='2024-10-11 14:25:10.487'
                           )
    argParser.add_argument('--FinalDateCtrl',
                           help='Data Final de Proceso.',
                           required=False,
                          default='2024-10-12 14:25:10.487'
                           )
    argParser.add_argument('--ProcessTable',
                           help='Tabela do Processo.',
                           required=True,
                           default='dbo.stageProcessoAbsenteismoPredicao'
                           )
    argParser.add_argument('--ProcessKey',
                           help='Número do Processo no DataCore.',
                           required=False,
                          default='0'
                           )
    argParser.add_argument('--connectionString',
                           help='Connection string for the database.',
                           required=True,
                           default='DRIVER=SQL Server;SERVER=server;DATABASE=db;UID=user;PWD=pass;TrustServerCertificate=yes;'
                           )
    argParser.add_argument('--dias_atras',
                           type=int,
                           help='Quantidade de dias para trás da data atual para delimitar a base de treinamento.',
                           default=90
                           )
    argParser.add_argument('--dias_frente',
                           type=int,
                           help='Quantidade de dias para frente da data atual para delimitar a base de treinamento.',
                           default=15
                           )
    argParser.add_argument('--dias_filtro_previsao',
                           type=int,
                           help='Quantidade de dias para trás da data de referência para filtrar as previsões a inserir.',
                           default=0
                           )
    argParser.add_argument('--evaluate_model',
                           action='store_true',
                           help='Se definido, executa avaliação completa do modelo com matriz de confusão e métricas.'
                           )

    args = argParser.parse_args() 
    rows = main()

    try:
        sys.stdout.write(str(rows))
        sys.stdout.flush()
        sys.exit(0x00)

    except Exception as error:
        exc_type, value, traceback = sys.exc_info()
        errmessage = "Failed: [%s] " % exc_type.__name__ + str(error)[:255]
        sys.stdout.write(errmessage)
        sys.stdout.flush()
        sys.exit(0x01)
