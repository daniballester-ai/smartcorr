import os
enable_venv = os.path.join(os.path.dirname(os.path.abspath(__file__)), r'venv\Scripts\activate_this.py')
exec(open(enable_venv).read(), {'__file__': enable_venv})
os.environ["LOKY_MAX_CPU_COUNT"] = "1"

import pandas as pd
import numpy as np
import pyodbc
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import  RandomizedSearchCV
from sklearn.metrics import classification_report, roc_auc_score
from datetime import datetime, timedelta
import warnings
from scipy.stats import randint
from imblearn.over_sampling import SMOTE
from credencial import SERVER_DEST, DATABASE_DEST, USERNAME_DEST, PASSWORD_DEST


warnings.filterwarnings('ignore')

class AbsenteeismPredictor:
    def __init__(self, server=SERVER_DEST, database=DATABASE_DEST, username=USERNAME_DEST, password=PASSWORD_DEST):
        self.server = server
        self.database = database
        self.model = RandomForestClassifier(n_estimators=200, random_state=42, class_weight='balanced')
        self.df = None
        self.expert_stats = None
        self.features = None
        
        # Configuração da conexão com pyodbc
        self.conn_str = (
            f'DRIVER=SQL Server;'
            f'SERVER={server};'
            f'DATABASE={database};'
            f'UID={username};'
            f'PWD={password};'
            f'TrustServerCertificate=yes;'
        )
        self.connection = pyodbc.connect(self.conn_str)
        self.cursor = self.connection.cursor()
 
    def execute_query(self, query):
        """Executa uma consulta SQL e retorna um DataFrame"""
        try:
            self.cursor.execute(query)
            columns = [column[0] for column in self.cursor.description]
            data = self.cursor.fetchall()
            return pd.DataFrame.from_records(data, columns=columns)
        except Exception as e:
            print(f"Erro ao executar consulta: {e}")
            raise
    
    def insert_data(self, df, table_name, schema='AbsGuard'):
        """Insere dados de um DataFrame em uma tabela"""
        try:
            # Verifica e ajusta os tipos de dados
            for col in df.columns:
                if df[col].dtype == 'object':
                    # Trunca strings muito longas
                    df[col] = df[col].astype(str).str.slice(0, 255)
                elif pd.api.types.is_datetime64_any_dtype(df[col]):
                    # Converte datas para string no formato SQL
                    df[col] = df[col].dt.strftime('%Y-%m-%d %H:%M:%S')

            # Prepara os placeholders para os valores
            columns = ', '.join([f'[{col}]' for col in df.columns])  # Adiciona colchetes para nomes de colunas
            placeholders = ', '.join(['?'] * len(df.columns))
        
            # Prepara a query SQL
            query = f"INSERT INTO {schema}.{table_name} ({columns}) VALUES ({placeholders})"
        
            # Converte os dados para tuplas
            data_tuples = [tuple(x) for x in df.to_numpy()]
        
            # Executa em lotes para melhor performance
            self.cursor.fast_executemany = True
            self.cursor.executemany(query, data_tuples)
            self.connection.commit()
            print("Dados inseridos com sucesso!")
        except Exception as e:
            self.connection.rollback()
            print(f"Erro ao inserir dados: {e}")
            print(f"Query que causou o erro: {query}")
            print("Primeiras linhas dos dados:")
            print(df.head())
            raise
    
    def truncate_table(self, table_name, v_where):
        """Limpa uma tabela com base em uma condição WHERE"""
        try:
            query = f"DELETE FROM {table_name} WHERE {v_where}"
            self.cursor.execute(query)
            self.connection.commit()
            print(f"Tabela {table_name} limpa com sucesso para os registros onde {v_where}")
        except Exception as e:
            self.connection.rollback()
            print(f"Erro ao limpar tabela: {e}")
            raise
    
    def __del__(self):
        """Fecha a conexão quando o objeto é destruído"""
        if hasattr(self, 'cursor'):
            self.cursor.close()
        if hasattr(self, 'connection'):
            self.connection.close()
    
    def load_data_from_db(self):
        """Carrega os dados diretamente do banco de dados"""
        query = """
       

        DECLARE @DT_HJ DATE = dateadd(day,35,GETDATE())
        DECLARE @DT_INI DATE = DATEADD(day, -100, @DT_HJ) 
        SET @DT_INI = DATEADD(DAY,-DATEPART(DAY,@DT_INI)+1,@DT_INI)

        
        SELECT distinct  g.DATE AS DATA,    g.CodeLevelServiceStructure3,       case when     g.ScheduledWorktime is null then datediff(second,g.AgentScheduleStart,g.AgentScheduleStop)
        else g.ScheduledWorktime end AS [TEMPO ESCALA],
        
            g.FpwIdHierarchyLevel1 AS [MATRICULA EXPERT]
            ,case when g.LackOfWorkday is null then 0 else g.LackOfWorkday end AS [FALTOU]
           ,ISNULL([dbo].[fncCalcula_Distancia_Coordenada](cl.Latitude,cl.Longitude,s.Latitude,s.Longitude),1)/1000 [DISTANCIA_DA_EMPRESA]   
           ,case when g.JustifiedEventFlag is null then 0 else g.JustifiedEventFlag end [FALTA_JUSTIFICADA]  
        FROM  [AbsGuard].[factMicroGestao] g with(nolock) 
            inner join [Tp_Analytics].[dbo].[OdsFpwBi_Employee] e with(nolock)  on e.FpwId=g.FpwIdHierarchyLevel1
			and e.CurrentCtrl=1
            INNER JOIN [Tp_Analytics].[AbsGuard].[dimPreditivoImplantacao] dp with(nolock)  on dp.[client_legacy]=g.CodeLevelServiceStructure3
            LEFT JOIN [Tp_Analytics].[dbo].[CepLatLong] cl on cl.[ZipCode]=g.CityCode
            LEFT JOIN [Tp_Analytics].[dbo].[SiteLatitudeLongitude] s on s.[SiteName]=e.SiteName
        WHERE 
            g.date BETWEEN @DT_INI AND @DT_HJ
            and dp.Data_Encerramento is null
            AND g.IsNewHire = 0
            AND case when     g.ScheduledWorktime is null then datediff(second,g.AgentScheduleStart,g.AgentScheduleStop)
        else g.ScheduledWorktime end > 0
            AND g.IsAbsenteeismNeutral = 0      and g.IsActiveEmployee=1
             
	
        """
        self.df = self.execute_query(query)
        print(f"Carregados {len(self.df)} registros do banco de dados.")
    
    def preprocess_data(self):
        """Pré-processamento dos dados"""
        
        if self.df is None:
            self.load_data_from_db()
        
        self.df['DATA'] = pd.to_datetime(self.df['DATA'])
        self.df['TARGET'] = self.df['FALTOU']
        #self.df['TEMPO_ESCALA_HORAS'] = self.df['TEMPO ESCALA'] / 3600
        self.df['DISTANCIA_DA_EMPRESA'] = self.df['DISTANCIA_DA_EMPRESA'].fillna(self.df['DISTANCIA_DA_EMPRESA'].median())
        self.df['DISTANCE_MEAN'] = self.df['DISTANCIA_DA_EMPRESA'].fillna(self.df['DISTANCIA_DA_EMPRESA'].mean())


        bins = [0, 2, 5, 10, 15, 30, 50, np.inf]
        labels = ['0-2km', '2-5km', '5-10km', '10-15km', '15-30km', '30-50km', '50+km']
        self.df['DISTANCIA_CATEGORIA'] = pd.cut(self.df['DISTANCIA_DA_EMPRESA'], bins=bins, labels=labels)
    
    def feature_engineering(self):
        """Engenharia de features para o modelo"""
        #self.df['DIA'] = self.df['DATA'].dt.day
        #self.df['MES'] = self.df['DATA'].dt.month
        self.df['DIA_DA_SEMANA'] = self.df['DATA'].dt.dayofweek
        self.df['FIM_DE_SEMANA'] = self.df['DIA_DA_SEMANA'].isin([5, 6]).astype(int)
        #self.df['DIA_DO_ANO'] = self.df['DATA'].dt.dayofyear
        
        self._calculate_expert_stats()
        
        self.features = [
            #'DIA', 'MES', 
            'DIA_DA_SEMANA'
            , 'FIM_DE_SEMANA',
            #, 'DIA_DO_ANO',
            'DISTANCIA_DA_EMPRESA',
            'TARGET_MEAN',
            'TARGET_STD',
            'TARGET_LAST',
            'TARGET_LAST_3',  # <- Nova feature aqui
            'COUNT',
            'RECENT_ABSENCES',
            'DISTANCE_MEAN'
        ]
        if 'DISTANCE_MEAN_x' in self.df.columns:
           self.df.rename(columns={'DISTANCE_MEAN_x': 'DISTANCE_MEAN'}, inplace=True)
        if 'DISTANCIA_DA_EMPRESA_x' in self.df.columns:
           self.df.rename(columns={'DISTANCIA_DA_EMPRESA_x': 'DISTANCIA_DA_EMPRESA'}, inplace=True)

    def _calculate_expert_stats(self):

        df_hist = self.df[self.df['DATA'] <= pd.to_datetime(datetime.now().date()) - timedelta(days=1)]

        agg_stats = df_hist.groupby(['MATRICULA EXPERT', 'CodeLevelServiceStructure3']).agg({
            'TARGET': ['mean', 'std', 'count'],
            'FALTA_JUSTIFICADA': 'mean',
                              
            'DISTANCIA_DA_EMPRESA': 'median',
            'DISTANCE_MEAN': 'mean'
        }).reset_index()
        
        agg_stats.columns = [
            'MATRICULA EXPERT', 'CodeLevelServiceStructure3',
            'TARGET_MEAN', 'TARGET_STD', 'COUNT',
            'FALTA_JUSTIFICADA',
            #'TEMPO_ESCALA_MEAN',
            'DISTANCIA_DA_EMPRESA','DISTANCE_MEAN'
            
        ]
        
        last_date = pd.to_datetime(datetime.now().date() - timedelta(days=1))
        #self.df['DATA'].max()
        

        date_threshold = last_date - timedelta(days=30)
        recent_stats = df_hist[df_hist['DATA'] > date_threshold].groupby(
            ['MATRICULA EXPERT', 'CodeLevelServiceStructure3']
        ).agg({'TARGET': 'mean'}).reset_index()

        recent_stats.columns = ['MATRICULA EXPERT', 'CodeLevelServiceStructure3', 'RECENT_ABSENCES']
        
        date_threshold_d = last_date - timedelta(days=10)
        last_d_stats = df_hist[df_hist['DATA'] > date_threshold_d].groupby(
            ['MATRICULA EXPERT', 'CodeLevelServiceStructure3']
        ).agg({'TARGET': 'mean'}).reset_index()
        last_d_stats.columns = ['MATRICULA EXPERT', 'CodeLevelServiceStructure3', 'TARGET_LAST']
        
        date_threshold_3 = pd.to_datetime(datetime.now().date()) - timedelta(days=3)
        last_3_stats = df_hist[df_hist['DATA'] > date_threshold_3].groupby(
            ['MATRICULA EXPERT', 'CodeLevelServiceStructure3']
            ).agg({'TARGET': 'mean'}).reset_index()
        last_3_stats.columns = ['MATRICULA EXPERT', 'CodeLevelServiceStructure3', 'TARGET_LAST_3']


        self.expert_stats = agg_stats.merge(
            recent_stats, on=['MATRICULA EXPERT', 'CodeLevelServiceStructure3']
        ).merge(
            last_d_stats, on=['MATRICULA EXPERT', 'CodeLevelServiceStructure3']
        )
        
        self.expert_stats = self.expert_stats.merge(
        last_3_stats, on=['MATRICULA EXPERT', 'CodeLevelServiceStructure3'], how='left'
    )

        self.df = self.df.merge(
            self.expert_stats,
            on=['MATRICULA EXPERT', 'CodeLevelServiceStructure3'],
            how='left'
        )

        for c in ['TARGET_MEAN', 'TARGET_STD', 'TARGET_LAST', 'TARGET_LAST_3', 'COUNT', 'RECENT_ABSENCES',
                  'DISTANCE_MEAN']:
            if c in self.df.columns:
                self.df[c] = self.df[c].fillna(0)

    def prepare_data(self, use_smote=False):
        last_date = pd.to_datetime(datetime.now().date() - timedelta(days=1))
        train_threshold = last_date - timedelta(days=7)

        df_work = self.df.copy()

        # filtro em cópia local (não muta self.df)
        df_work = df_work[df_work['TEMPO ESCALA'] > 0].copy()

        # TARGET obrigatório e sem NaN
        df_work = df_work[df_work['TARGET'].notna()].copy()
        df_work['TARGET'] = pd.to_numeric(df_work['TARGET'], errors='coerce')
        df_work = df_work[df_work['TARGET'].notna()].copy()
        df_work['TARGET'] = df_work['TARGET'].astype(int)

        X_train = df_work[df_work['DATA'] < train_threshold][self.features].copy()
        y_train = df_work[df_work['DATA'] < train_threshold]['TARGET'].copy()

        X_test = df_work[df_work['DATA'] >= train_threshold][self.features].copy()
        y_test = df_work[df_work['DATA'] >= train_threshold]['TARGET'].copy()

        X_train.fillna(0, inplace=True)
        X_test.fillna(0, inplace=True)

        # validações
        if X_test.empty or y_test.empty:
            print("Aviso: Sem dados de teste após filtros. Operação será treinada sem avaliação.")
            X_test = pd.DataFrame(columns=self.features)
            y_test = pd.Series(dtype='int64')

        if y_train.isna().any():
            raise ValueError("y_train contém NaN após limpeza.")
        if y_train.nunique() < 2:
            raise ValueError("Treino com apenas 1 classe após recorte temporal.")

        if use_smote:
            smote = SMOTE(random_state=42)
            X_train, y_train = smote.fit_resample(X_train, y_train)
            print("\n Dados balanceados com SMOTE")
            print(f"Novo tamanho do treino: {len(X_train)}")
            print(f"Distribuição após SMOTE:\n{pd.Series(y_train).value_counts(normalize=True)}")

        return X_train, X_test, y_train, y_test

    def tune_hyperparameters(self, use_smote=False):
        """Otimiza os hiperparâmetros com foco em recall e AUC-ROC"""
        X_train, X_test, y_train, y_test = self.prepare_data(use_smote=use_smote)

        # Espaço de parâmetros expandido e ajustado
        param_dist = {
            'n_estimators': randint(50, 200),
            'max_depth': [None, 5, 10, 15, 20, 30],
            'min_samples_split': randint(2, 20),
            'min_samples_leaf': randint(1, 10),
            'bootstrap': [True, False],
            'class_weight': ['balanced', 'balanced_subsample', {0: 1, 1: 5}],
            'max_features': ['sqrt', 'log2', None],
            'criterion': ['gini', 'entropy']
        }

        rf = RandomForestClassifier(random_state=42)
        random_search = RandomizedSearchCV(
            rf,
            param_distributions=param_dist,
            n_iter=50,
            cv=3,
            scoring='recall',
            verbose=1,
            n_jobs=-1,
            random_state=42,
            return_train_score=True
        )

        print("\n Otimização avançada de hiperparâmetros...")
        random_search.fit(X_train, y_train)

        self.model = random_search.best_estimator_

        print("\n Melhores parâmetros encontrados:")
        print(random_search.best_params_)
        print(f"\n Melhor score na validação (recall): {random_search.best_score_:.4f}")

        # Só avalia se houver teste válido
        if len(X_test) > 0 and len(y_test) > 0 and pd.Series(y_test).nunique() >= 2:
            print("\n Performance no conjunto de teste:")
            self._evaluate_model(X_test, y_test)
        else:
            print("\n Sem conjunto de teste válido para avaliação nesta operação (modelo treinado mesmo assim).")
    
    def _evaluate_model(self, X_test, y_test):
        """Avaliação detalhada com métricas adicionais"""
        from sklearn.metrics import confusion_matrix, precision_recall_curve, average_precision_score
    
        y_proba = self.model.predict_proba(X_test)[:, 1]
        y_pred =  (y_proba > 0.3).astype(int)
        
    
        # Matriz de confusão
        cm = confusion_matrix(y_test, y_pred)
        print("\n Matriz de Confusão:")
        print(f"Verdadeiros Negativos: {cm[0,0]} | Falsos Positivos: {cm[0,1]}")
        print(f"Falsos Negativos: {cm[1,0]}  | Verdadeiros Positivos: {cm[1,1]}")
    
        # Relatório completo
        print("\n Relatório de Classificação:")
        print(classification_report(y_test, y_pred, digits=4))
    
        # Métricas adicionais
        print(f"\n AUC-ROC: {roc_auc_score(y_test, y_proba):.4f}")
        print(f" AUC-PR: {average_precision_score(y_test, y_proba):.4f}")
    
        # Feature importance
        print("\n Importância das Features:")
        for feature, importance in sorted(zip(self.features, self.model.feature_importances_), 
                                        key=lambda x: x[1], reverse=True):
            print(f"{feature:20}: {importance:.4f}")

    def train_model_por_operacao(self, tune_hyperparams=False, use_smote=False):
        resultados = []

        operacoes = self.df['CodeLevelServiceStructure3'].dropna().unique().tolist()

        for operacao in operacoes:
            print(f"\nTreinando modelo para operação: {operacao}")
            df_op = self.df[self.df['CodeLevelServiceStructure3'] == operacao].copy()

            # Verifique TARGET da operação atual (sem NaN)
            y_op = df_op['TARGET'].dropna()
            if y_op.nunique() < 2:
                print(f"Operação {operacao} não tem classes suficientes para treinamento. Pulando.")
                continue

            df_backup = self.df.copy()
            self.df = df_op.reset_index(drop=True)

            try:
                X_train, X_test, y_train, y_test = self.prepare_data(use_smote=use_smote)

                print(f"Treino={len(X_train)} | Teste={len(X_test)} | "
                      f"Classes treino={y_train.dropna().nunique()} | NaN y_train={y_train.isna().sum()}")

                if tune_hyperparams:
                    self.tune_hyperparameters(use_smote=use_smote)
                else:
                    self.model = RandomForestClassifier(
                        n_estimators=200,
                        max_depth=10,
                        min_samples_split=8,
                        min_samples_leaf=2,
                        class_weight='balanced',
                        bootstrap=True,
                        n_jobs=-1,
                        random_state=42
                    )
                    self.model.fit(X_train, y_train)

                print(f"\nModelo treinado para operação {operacao}.")
                previsao_op = self.predict_absenteeism(codigo_cliente=operacao)

                if previsao_op is not None and not previsao_op.empty:
                    resultados.append(previsao_op)

            except Exception as e:
                print(f"Erro na operação {operacao}: {e}")

            finally:
                # GARANTE restauração mesmo se der erro
                self.df = df_backup

        if resultados:
            return pd.concat(resultados, ignore_index=True)

        # já devolve colunas esperadas para evitar KeyError depois
        return pd.DataFrame(columns=[
            'MATRICULA EXPERT', 'CodeLevelServiceStructure3', 'DATA_PREVISAO',
            'PREVISAO_ABS', 'PROBABILIDADE', 'DISTANCE_MEAN'
        ])


    def train_model(self, tune_hyperparams=False, use_smote=False):
        """Treina o modelo com opções avançadas"""
        X_train, X_test, y_train, y_test = self.prepare_data(use_smote=use_smote)
    
        print("\n Distribuição original do target:")
        print(y_train.value_counts(normalize=True))
    
        if tune_hyperparams:
            self.tune_hyperparameters()
        else:
            # Configuração otimizada baseada nos melhores parâmetros encontrados
            self.model = RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                min_samples_split=8,
                min_samples_leaf=2,
                class_weight='recall',
                bootstrap=True,
                n_jobs=-1,
                random_state=42
            )
            self.model.fit(X_train, y_train)
    
        print("\n Métricas de avaliação:")
        self._evaluate_model(X_test, y_test)
    
    def predict_absenteeism(self, codigo_cliente):
        days_ahead=141
        if self.expert_stats is None:
           raise ValueError("Dados não carregados. Execute load_data_from_db() primeiro.")

        hoje = pd.to_datetime(datetime.now().date() - timedelta(days=5))
        
        # Seleciona somente registros com escala futura (> hoje) e tempo de escala > 0
        df_futuro = self.df[
            (self.df['DATA'] >= hoje) &
            (self.df['TEMPO ESCALA'] > 0)
        ].copy()

        if df_futuro.empty:
            print("Nenhuma escala futura encontrada com tempo > 0.")
            return pd.DataFrame()

        df_futuro = df_futuro.merge(self.expert_stats, on=['MATRICULA EXPERT', 'CodeLevelServiceStructure3'], how='left')

        #df_futuro['DIA'] = df_futuro['DATA'].dt.day
        #df_futuro['MES'] = df_futuro['DATA'].dt.month
        df_futuro['DIA_DA_SEMANA'] = df_futuro['DATA'].dt.dayofweek
        df_futuro['FIM_DE_SEMANA'] = df_futuro['DIA_DA_SEMANA'].isin([5, 6]).astype(int)
        #df_futuro['DIA_DO_ANO'] = df_futuro['DATA'].dt.dayofyear
        #df_futuro['TEMPO_ESCALA_HORAS'] = df_futuro['TEMPO ESCALA'] / 3600
        if 'TARGET_LAST_3_x' in df_futuro.columns:
             df_futuro.rename(columns={'TARGET_LAST_3_x': 'TARGET_LAST_3'}, inplace=True)       
        


        if 'DISTANCE_MEAN_x' in df_futuro.columns:
           df_futuro.rename(columns={'DISTANCE_MEAN_x': 'DISTANCE_MEAN'}, inplace=True)
        if 'DISTANCIA_DA_EMPRESA_x' in df_futuro.columns:
           df_futuro.rename(columns={'DISTANCIA_DA_EMPRESA_x': 'DISTANCIA_DA_EMPRESA'}, inplace=True)
        if 'TARGET_MEAN_x' in df_futuro.columns:
           df_futuro.rename(columns={'TARGET_MEAN_x': 'TARGET_MEAN'}, inplace=True)
           df_futuro.rename(columns={'TARGET_STD_x': 'TARGET_STD'}, inplace=True)
           df_futuro.rename(columns={'TARGET_LAST_x': 'TARGET_LAST'}, inplace=True)
        if 'COUNT_x' in df_futuro.columns:
           df_futuro.rename(columns={'COUNT_x': 'COUNT'}, inplace=True)           
        if 'RECENT_ABSENCES_x' in df_futuro.columns:
           df_futuro.rename(columns={'RECENT_ABSENCES_x': 'RECENT_ABSENCES'}, inplace=True)           


        X_pred = df_futuro[self.features].copy()

        df_futuro['PREVISAO_ABS'] = self.model.predict(X_pred)
        df_futuro['PROBABILIDADE'] = self.model.predict_proba(X_pred)[:, 1]
        
        custom_threshold = 0.80  # exemplo

        codigo_cliente_str = str(codigo_cliente)

        if codigo_cliente_str == '3230':
            custom_threshold = 0.88
        elif codigo_cliente_str == '2721':
            custom_threshold = 0.75
        elif codigo_cliente_str == '2379':
            custom_threshold = 0.71

        df_futuro['PREVISAO_ABS'] = (df_futuro['PROBABILIDADE'] >= custom_threshold).astype(int)

      

        resultado = df_futuro[[
            'MATRICULA EXPERT', 'CodeLevelServiceStructure3', 'DATA',
            'PREVISAO_ABS', 'PROBABILIDADE', 'DISTANCE_MEAN'
        ]].rename(columns={
            'DATA': 'DATA_PREVISAO'
        })

        return resultado.sort_values(['DATA_PREVISAO', 'PROBABILIDADE'], ascending=[True, False])

if __name__ == "__main__":

    print("\n Iniciando processo de preditivo...")
    predictor = AbsenteeismPredictor()
    
    # 1. Carregar e preparar dados
    predictor.load_data_from_db()
    predictor.preprocess_data()
    predictor.feature_engineering()
    
    # 2. Treinar com SMOTE e tuning (executar apenas uma vez para encontrar melhores parâmetros)
    print("\n Executando com SMOTE e tuning de hiperparâmetros...")
    #predictor.train_model(tune_hyperparams=True, use_smote=True)
    
    # 3. Depois de encontrar os melhores parâmetros, você pode usar:
    # predictor.train_model(tune_hyperparams=False, use_smote=True)
    
    # Restante do código permanece igual...
    resultado = predictor.train_model_por_operacao(tune_hyperparams=True, use_smote=True)

    if resultado is None or resultado.empty:
        print("Nenhuma predição gerada. Encerrando sem inserir no banco.")
        raise SystemExit(0)

    df_pred_insert = resultado.rename(columns={
        'MATRICULA EXPERT': 'Matricula_Expert',
        'DATA_PREVISAO': 'Data_da_Escala',
        'PREVISAO_ABS': 'Previsto_Ausencia',
        'PROBABILIDADE': 'Probabilidade_de_Ausencia',
        'CodeLevelServiceStructure3': 'CodeLevelServiceStructure3'
    })

    colunas_obrigatorias = [
        'Matricula_Expert', 'Data_da_Escala',
        'Previsto_Ausencia', 'Probabilidade_de_Ausencia', 'CodeLevelServiceStructure3'
    ]

    faltantes = [c for c in colunas_obrigatorias if c not in df_pred_insert.columns]
    if faltantes:
        print(f"Sem colunas esperadas nas predições: {faltantes}")
        raise SystemExit(0)


    df_pred_insert = df_pred_insert[
    (df_pred_insert['Data_da_Escala'] >= pd.to_datetime(datetime.now().date() - timedelta(days=5))) & 
    (df_pred_insert['Previsto_Ausencia'] > 0)
    ][[
        'Matricula_Expert',
        'Data_da_Escala',
        'Previsto_Ausencia',
        'Probabilidade_de_Ausencia',
        'CodeLevelServiceStructure3'
    ]]
    df_pred_insert['Data_da_Escala'] = pd.to_datetime(df_pred_insert['Data_da_Escala'])

    print("\n Previsões para inserção no banco:")
    
    # Data_da_Escala < CONVERT(DATE,GETDATE())
    db_manager = AbsenteeismPredictor()
    db_manager.truncate_table("[Tp_Analytics].[AbsGuard].[Previsao_Absenteismo]"," Data_da_Escala >= CONVERT(DATE,dateadd(day,-5,GETDATE())) ")
    df_pred_insert['Data_da_Escala'] = pd.to_datetime(df_pred_insert['Data_da_Escala']).dt.strftime('%Y-%m-%d')
    # Verifica os tipos e tamanhos antes da inserção 

    for col in df_pred_insert.select_dtypes(include=['object']).columns:
        print(f"{col}: {df_pred_insert[col].str.len().max()}")


    print(df_pred_insert)

    db_manager.insert_data(df_pred_insert, 'Previsao_Absenteismo')

    print("\n Executando procedure [AbsGuard].[PrevisaoAbs_CompletaTabela]...")
    try:
        db_manager.cursor.execute("EXEC [AbsGuard].[PrevisaoAbs_CompletaTabela]")
        db_manager.connection.commit()
        print("Procedure executada com sucesso!")
    except Exception as e:
        db_manager.connection.rollback()
        print(f"Erro ao executar procedure: {e}")
        raise

    print("\n Executando procedure [AbsGuard].[ProcAvisoPreditivoSupervisor]...")
    try:
        db_manager.cursor.execute("EXEC [AbsGuard].[ProcAvisoPreditivoSupervisor]")
        db_manager.connection.commit()
        print("Procedure executada com sucesso!")
    except Exception as e:
        db_manager.connection.rollback()
        print(f"Erro ao executar procedure: {e}")
        raise    

    