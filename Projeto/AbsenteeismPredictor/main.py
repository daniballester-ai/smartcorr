import os
import sys
import pandas as pd
import numpy as np
import pyodbc
from datetime import datetime, timedelta
import warnings
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import RandomizedSearchCV
from sklearn.metrics import classification_report, roc_auc_score, confusion_matrix, accuracy_score, precision_score, recall_score, f1_score
from xgboost import XGBClassifier
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOTTING_LIBS = True
except ImportError:
    HAS_PLOTTING_LIBS = False
    print("Aviso: matplotlib e seaborn não estão disponíveis. A matriz de confusão não será plotada.")
from imblearn.over_sampling import SMOTE

warnings.filterwarnings('ignore')

class AbsenteeismPredictor:
    def __init__(self, connection_string, dias_atras=30, dias_frente=7, process_table=None, process_key=None, final_date_ctrl=None, dias_filtro_previsao=5):
        self.conn_str = connection_string
        self.dias_atras = dias_atras
        self.dias_frente = dias_frente
        self.process_table = process_table
        self.process_key = process_key
        self.final_date_ctrl = self._parse_final_date(final_date_ctrl)
        self.dias_filtro_previsao = dias_filtro_previsao
        self.connection = pyodbc.connect(self.conn_str)
        self.cursor = self.connection.cursor()
        self.df = None
        self.features = None
        self.model = RandomForestClassifier(n_estimators=200, random_state=42, class_weight='balanced')
        self.df_pred_insert = None

    def _parse_final_date(self, final_date_ctrl):
        if final_date_ctrl is None:
            return datetime.now().date()
        parsed = pd.to_datetime(final_date_ctrl, errors='coerce')
        if pd.isna(parsed):
            raise ValueError(f"FinalDateCtrl inválido: {final_date_ctrl}")
        return parsed.date()
 
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
    
    def _validate_required_columns(self, required_columns):
        """Verifica se o DataFrame contém as colunas obrigatórias."""
        missing = [col for col in required_columns if col not in self.df.columns]
        if missing:
            raise ValueError(
                f"Colunas obrigatórias ausentes no DataFrame: {missing}. "
                f"Colunas disponíveis: {list(self.df.columns)}"
            )

    def _normalize_column_names(self):
        """Aplica nomes de coluna esperados a partir de aliases comuns."""
        rename_map = {}
        if 'date' in self.df.columns and 'DATA' not in self.df.columns:
            rename_map['date'] = 'DATA'
        if 'LackOfWorkday' in self.df.columns and 'FALTOU' not in self.df.columns:
            rename_map['LackOfWorkday'] = 'FALTOU'
        if 'JustifiedEventFlag' in self.df.columns and 'FALTA_JUSTIFICADA' not in self.df.columns:
            rename_map['JustifiedEventFlag'] = 'FALTA_JUSTIFICADA'
        if rename_map:
            self.df.rename(columns=rename_map, inplace=True)


    def load_data_from_db(self):
        """Carrega os dados diretamente do banco de dados"""
        # Read query from SQL file
        sql_file_path = os.path.join(os.path.dirname(__file__), '..', 'sql', 'Base_treinamento_dev.sql')
        with open(sql_file_path, 'r', encoding='utf-8') as f:
            query = f.read()
        
        # Calcular datas usando FinalDateCtrl como referência
        hoje = self.final_date_ctrl
        start_date = hoje - timedelta(days=self.dias_atras)
        end_date = hoje + timedelta(days=self.dias_frente)
        
        # Substituir placeholders na query
        query = query.replace('{{data_inicial}}', start_date.isoformat())
        query = query.replace('{{data_final}}', end_date.isoformat())
        
        self.df = self.execute_query(query)
        print(f"Carregados {len(self.df)} registros do banco de dados com filtro de datas ({start_date} a {end_date}).")
    
    def _calculate_distance_haversine(self, lat1, lon1, lat2, lon2):
        """
        Calcula a distância em km entre dois pontos usando a fórmula Haversine.
        
        Args:
            lat1, lon1: Latitude e longitude do ponto 1
            lat2, lon2: Latitude e longitude do ponto 2
        
        Returns:
            Distância em km, 10km se dados zerados, ou NaN se não conseguir calcular
        """
        try:
            # Converter para float
            lat1 = float(lat1)
            lon1 = float(lon1)
            lat2 = float(lat2)
            lon2 = float(lon2)
            
            # Validar se não são NaN
            if np.isnan(lat1) or np.isnan(lon1) or np.isnan(lat2) or np.isnan(lon2):
                return np.nan
            
            # Se ambos os pontos têm coordenadas zeradas (dados nulos convertidos), arbitrar 10km
            if (lat1 == 0 and lon1 == 0) or (lat2 == 0 and lon2 == 0):
                return 10.0
            
            R = 6371  # Raio da Terra em km
            
            # Converte para radianos
            lat1_rad = np.radians(lat1)
            lon1_rad = np.radians(lon1)
            lat2_rad = np.radians(lat2)
            lon2_rad = np.radians(lon2)
            
            # Diferenças
            dlat = lat2_rad - lat1_rad
            dlon = lon2_rad - lon1_rad
            
            # Fórmula Haversine
            a = np.sin(dlat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon/2)**2
            c = 2 * np.arctan2(np.sqrt(a), np.sqrt(1-a))
            distance = R * c
            
            return distance
        
        except (ValueError, TypeError) as e:
            print(f"Aviso: Erro ao calcular distância entre ({lat1}, {lon1}) e ({lat2}, {lon2}): {e}")
            return np.nan
    
    def preprocess_data(self):
        """Pré-processamento dos dados"""
        
        if self.df is None:
            self.load_data_from_db()

        self._normalize_column_names()
        self._validate_required_columns([
            'DATA', 'FALTOU', 'CodeLevelServiceStructure3',
            'FpwIdHierarchyLevel1', 'latExp', 'longExp', 'latSite', 'longSite'
        ])

        # Converter DATA para datetime
        self.df['DATA'] = pd.to_datetime(self.df['DATA'])
        
        # Criar coluna TARGET a partir de FALTOU
        self.df['TARGET'] = self.df['FALTOU']
        
        # Garantir que as colunas de latitude/longitude são float
        for col in ['latExp', 'longExp', 'latSite', 'longSite']:
            if col in self.df.columns:
                self.df[col] = pd.to_numeric(self.df[col], errors='coerce')
        
        # Coluna derivada da nova coluna vinda do banco (hiredmonths)
        if 'hiredmonths' in self.df.columns:
            self.df['hiredmonths'] = pd.to_numeric(self.df['hiredmonths'], errors='coerce').fillna(0)
            self.df['HIREDMONTHS_LOG'] = np.log1p(self.df['hiredmonths'].clip(lower=0))
        
        # Calcular distância Haversine entre os pontos de latitude e longitude
        # latExp, longExp: localização do funcionário
        # latSite, longSite: localização do site/empresa
        self.df['DISTANCIA_DA_EMPRESA'] = self.df.apply(
            lambda row: self._calculate_distance_haversine(
                row.get('latExp'), row.get('longExp'), 
                row.get('latSite'), row.get('longSite')
            ),
            axis=1
        )
        
        # Preencher valores faltantes (NaN) com a mediana
        median_dist = self.df['DISTANCIA_DA_EMPRESA'].median()
        if pd.isna(median_dist):
            # Se não houver valores válidos para calcular mediana, usar 0
            median_dist = 0
        self.df['DISTANCIA_DA_EMPRESA'] = self.df['DISTANCIA_DA_EMPRESA'].fillna(median_dist)
        
        # Calcular a média de distância
        mean_dist = self.df['DISTANCIA_DA_EMPRESA'].mean()
        if pd.isna(mean_dist):
            mean_dist = 0
        self.df['DISTANCE_MEAN'] = mean_dist
        
        # Criar categorias de distância
        bins = [0, 2, 5, 10, 15, 30, 50, np.inf]
        labels = ['0-2km', '2-5km', '5-10km', '10-15km', '15-30km', '30-50km', '50+km']
        self.df['DISTANCIA_CATEGORIA'] = pd.cut(self.df['DISTANCIA_DA_EMPRESA'], bins=bins, labels=labels)
    
    def feature_engineering(self):
        """Engenharia de features focada no comportamento individual e contexto do setor"""
        
        # 1. Features Temporais Básicas
        self.df['DIA_DA_SEMANA'] = self.df['DATA'].dt.dayofweek
        self.df['FIM_DE_SEMANA'] = self.df['DIA_DA_SEMANA'].isin([5, 6]).astype(int)
        
        # 2. Ordenação crucial para janelas móveis (Time Series Context)
        # Ordenar por especialista e data para garantir que shift/rolling funcionem corretamente
        self.df = self.df.sort_values(['FpwIdHierarchyLevel1', 'DATA']).reset_index(drop=True)
        
        # 3. Comportamento Individual (Features de histórico pessoal)
        # Média de faltas histórica do indivíduo até o dia anterior (excludente para não vazar dados)
        self.df['TARGET_MEAN_INDIVIDUAL'] = self.df.groupby('FpwIdHierarchyLevel1')['TARGET'].transform(
            lambda x: x.shift(1).expanding().mean()
        )
        
        # Soma de faltas nos últimos 7 e 30 dias (Densidade de faltas - padrão de comportamento)
        self.df['ROLLING_ABSENCES_7D'] = self.df.groupby('FpwIdHierarchyLevel1')['TARGET'].transform(
            lambda x: x.shift(1).rolling(window=7, min_periods=1).sum()
        )
        self.df['ROLLING_ABSENCES_30D'] = self.df.groupby('FpwIdHierarchyLevel1')['TARGET'].transform(
            lambda x: x.shift(1).rolling(window=30, min_periods=1).sum()
        )
        
        self.df['TENDENCIA'] = (self.df['ROLLING_ABSENCES_7D'] / 7) - (self.df['ROLLING_ABSENCES_30D'] / 30)
        self.df['HIREDMONTHS_GRUPO'] = pd.cut(
            self.df['hiredmonths'],
            bins=[0, 3, 12, 60],
            labels=[0, 1, 2],
            include_lowest=True
        ).astype(float)
        # Feature: Faltou no dia anterior (indicador forte de recorrência - padrão do indivíduo)
        self.df['FALTOU_DIA_ANTERIOR'] = self.df.groupby('FpwIdHierarchyLevel1')['TARGET'].transform(
            lambda x: x.shift(1)
        )
        
        # Feature: Sinal de risco acumulado (urgencia de comportamento de abandono)
        self.df['SINAL_DE_RISCO'] = self.df['ROLLING_ABSENCES_7D'] + (self.df['FALTOU_DIA_ANTERIOR'] * 2)
        
        # Feature: Faltou há 7 dias (preditor forte para recorrência semanal)
        self.df['LAG_7_DIAS'] = self.df.groupby('FpwIdHierarchyLevel1')['TARGET'].transform(
            lambda x: x.shift(7)
        )
        
        # Feature: Distância ponderada por dia da semana (pesa mais segunda ou sexta?)
        self.df['DISTANCIA_X_DIA_SEMANA'] = self.df['DISTANCIA_DA_EMPRESA'] * self.df['DIA_DA_SEMANA'].isin([0, 4]).astype(int)
        
        # Feature: Quantas pessoas da mesma operação faltaram no dia anterior
        daily_absences = self.df.groupby(['CodeLevelServiceStructure3', 'DATA'])['TARGET'].sum().reset_index()
        daily_absences.rename(columns={'TARGET': 'ABSENCES_OPERACAO_DIA'}, inplace=True)
        daily_absences['ABSENCES_OPERACAO_DIA_ANTERIOR'] = daily_absences.groupby('CodeLevelServiceStructure3')['ABSENCES_OPERACAO_DIA'].shift(1)
        self.df = self.df.merge(daily_absences[['CodeLevelServiceStructure3', 'DATA', 'ABSENCES_OPERACAO_DIA_ANTERIOR']], 
                               on=['CodeLevelServiceStructure3', 'DATA'], how='left')
        
        # 4. Chamar estatísticas de contexto (Setor/Escala)
        self._calculate_expert_stats()
        
        # 5. Lista de Features Atualizada (combinando individual + contexto setorial)
        self.features = [
            'DIA_DA_SEMANA', 
            'FIM_DE_SEMANA', 
            'DISTANCIA_DA_EMPRESA',
            'HIREDMONTHS_GRUPO',
            'LAG_7_DIAS',
            'DISTANCIA_X_DIA_SEMANA',
            'TARGET_MEAN_INDIVIDUAL',
            'ROLLING_ABSENCES_7D',
            'SINAL_DE_RISCO',
            'TENDENCIA',
            'ABSENCES_OPERACAO_DIA_ANTERIOR',
            'ROLLING_ABSENCES_30D',
            'RECENT_ABSENCES_SETOR', 
            'COUNT_SETOR'
        ]
        
        # Tratamento de valores NaN resultantes de shift/rolling
        # Preencher apenas colunas numéricas com 0, evitar preenchimento de colunas categóricas
        numeric_cols = self.df.select_dtypes(include=[np.number]).columns
        for col in numeric_cols:
            self.df[col] = self.df[col].fillna(0)
        
        # Tratar colunas duplicadas que podem surgir de merges
        if 'DISTANCE_MEAN_x' in self.df.columns:
            self.df.rename(columns={'DISTANCE_MEAN_x': 'DISTANCE_MEAN'}, inplace=True)
        if 'DISTANCIA_DA_EMPRESA_x' in self.df.columns:
            self.df.rename(columns={'DISTANCIA_DA_EMPRESA_x': 'DISTANCIA_DA_EMPRESA'}, inplace=True)
    
    def _calculate_expert_stats(self):
        """Calcula o comportamento médio do setor para dar contexto ao modelo individual"""
        
        reference_date = pd.to_datetime(self.final_date_ctrl)
        # Dados estritamente anteriores à data de predição (evitar data leakage)
        df_hist = self.df[self.df['DATA'] < reference_date].copy()
        
        if df_hist.empty:
            print("Aviso: Dados históricos vazios. Preenchendo com 0.")
            # Criar colunas vazias com 0 para evitar erros
            group_cols = ['FpwIdHierarchyLevel1', 'CodeLevelServiceStructure3']
            self.df['TARGET_MEAN_SETOR'] = 0
            self.df['COUNT_SETOR'] = 0
            self.df['DISTANCIA_MEDIA_SETOR'] = 0
            self.df['RECENT_ABSENCES_SETOR'] = 0
            return
        
        # Agrupamento por Setor/Operação (contexto da equipe)
        group_cols = ['FpwIdHierarchyLevel1', 'CodeLevelServiceStructure3']
        
        # Agregações gerais (histórico completo do setor)
        agg_stats = df_hist.groupby(group_cols).agg({
            'TARGET': ['mean', 'count'],
            'DISTANCIA_DA_EMPRESA': 'mean'
        }).reset_index()
        
        # Flattening de colunas MultiIndex
        agg_stats.columns = group_cols + ['TARGET_MEAN_SETOR', 'COUNT_SETOR', 'DISTANCIA_MEDIA_SETOR']
        
        # Estatísticas recentes do SETOR (últimos 30 dias) para capturar "surtos" ou sazonalidade
        if len(df_hist) > 0:
            last_date = df_hist['DATA'].max()
            recent_setor = df_hist[df_hist['DATA'] > (last_date - timedelta(days=30))].groupby(group_cols).agg({
                'TARGET': 'mean'
            }).reset_index()
            recent_setor.columns = group_cols + ['RECENT_ABSENCES_SETOR']
        else:
            recent_setor = pd.DataFrame(columns=group_cols + ['RECENT_ABSENCES_SETOR'])
        
        # Merge de volta ao DF principal (left join para manter todos os registros)
        context_stats = agg_stats.merge(recent_setor, on=group_cols, how='left')
        
        self.df = self.df.merge(context_stats, on=group_cols, how='left')
        
        # Preencher valores NaN com 0 (setores sem dados históricos)
        fill_columns = ['TARGET_MEAN_SETOR', 'COUNT_SETOR', 'DISTANCIA_MEDIA_SETOR', 'RECENT_ABSENCES_SETOR']
        for col in fill_columns:
            if col in self.df.columns:
                self.df[col] = self.df[col].fillna(0)
    
    def prepare_data(self, use_smote=False):
        """Prepara X e y para treino e teste"""
        self._validate_required_columns(['ScheduledWorktime', 'TARGET', 'DATA'])
        reference_date = pd.to_datetime(self.final_date_ctrl)
        train_threshold = pd.to_datetime((reference_date - timedelta(days=self.dias_filtro_previsao)).date())

        df_work = self.df.copy()
        df_work = df_work[df_work['ScheduledWorktime'] > 0].copy()
        df_work = df_work[df_work['TARGET'].notna()].copy()
        df_work['TARGET'] = pd.to_numeric(df_work['TARGET'], errors='coerce')
        df_work = df_work[df_work['TARGET'].notna()].copy()
        df_work['TARGET'] = df_work['TARGET'].astype(int)

        # Debug: Imprimir informações sobre as datas
        print(f"Data mínima no df_work: {df_work['DATA'].min()}")
        print(f"Data máxima no df_work: {df_work['DATA'].max()}")
        print(f"Train threshold: {train_threshold}")
        print(f"Total registros após filtros: {len(df_work)}")
        print(f"Registros com DATA < train_threshold: {len(df_work[df_work['DATA'] < train_threshold])}")
        print(f"Registros com DATA >= train_threshold: {len(df_work[df_work['DATA'] >= train_threshold])}")

        X_train = df_work[df_work['DATA'] < train_threshold][self.features].copy()
        y_train = df_work[df_work['DATA'] < train_threshold]['TARGET'].copy()
        X_test = df_work[df_work['DATA'] >= train_threshold][self.features].copy()
        y_test = df_work[df_work['DATA'] >= train_threshold]['TARGET'].copy()

        X_train.fillna(0, inplace=True)
        X_test.fillna(0, inplace=True)

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
            print("\nDados balanceados com SMOTE")
            print(f"Novo tamanho do treino: {len(X_train)}")
            print(f"Distribuição após SMOTE:\n{pd.Series(y_train).value_counts(normalize=True)}")

        return X_train, X_test, y_train, y_test
    
    def _evaluate_model(self, X_test, y_test):
        """Avalia o modelo no conjunto de teste"""
        if len(X_test) == 0 or len(y_test) == 0 or y_test.nunique() < 2:
            print("Avaliação ignorada: conjunto de teste inválido ou mono-classe.")
            return

        y_proba = self.model.predict_proba(X_test)[:, 1]
        y_pred = (y_proba > 0.3).astype(int)
        print("\nRelatório de classificação:")
        print(classification_report(y_test, y_pred, digits=4))
        print(f"AUC-ROC: {roc_auc_score(y_test, y_proba):.4f}")

    def tune_hyperparameters(self, use_smote=False):
        X_train, X_test, y_train, y_test = self.prepare_data(use_smote=use_smote)

        param_dist = {
            'n_estimators': [100, 150, 200],
            'max_depth': [None, 5, 10, 15],
            'min_samples_split': [2, 5, 10],
            'min_samples_leaf': [1, 2, 4],
            'bootstrap': [True, False],
            'class_weight': ['balanced', 'balanced_subsample'],
            'max_features': ['sqrt', 'log2', None],
            'criterion': ['gini', 'entropy']
        }

        rf = RandomForestClassifier(random_state=42)
        random_search = RandomizedSearchCV(
            rf,
            param_distributions=param_dist,
            n_iter=25,
            cv=3,
            scoring='recall',
            verbose=0,
            n_jobs=-1,
            random_state=42,
            return_train_score=True
        )

        print("\nOtimização de hiperparâmetros...")
        random_search.fit(X_train, y_train)
        self.model = random_search.best_estimator_
        print(f"Melhores parâmetros: {random_search.best_params_}")
        if len(X_test) > 0 and y_test.nunique() >= 2:
            self._evaluate_model(X_test, y_test)

    def evaluate_overall_model(self, use_smote=False, plot_confusion_matrix=True):
        """Avalia o modelo geral coletando dados de teste de todas as operações"""
        self._validate_required_columns(['CodeLevelServiceStructure3', 'TARGET', 'ScheduledWorktime', 'DATA', 'FpwIdHierarchyLevel1'])
        
        all_y_true = []
        all_y_pred = []
        all_y_proba = []
        
        operacoes = self.df['CodeLevelServiceStructure3'].dropna().unique().tolist()
        operacoes_com_teste = 0
        
        print("\n" + "="*60)
        print("AVALIAÇÃO GERAL DO MODELO")
        print("="*60)
        
        for operacao in operacoes:
            print(f"\nAvaliando operação: {operacao}")
            df_op = self.df[self.df['CodeLevelServiceStructure3'] == operacao].copy()
            y_op = df_op['TARGET'].dropna()
            
            if y_op.nunique() < 2:
                print(f"Operação {operacao} não tem classes suficientes para avaliação. Pulando.")
                continue

            df_backup = self.df
            self.df = df_op.reset_index(drop=True)

            try:
                X_train, X_test, y_train, y_test = self.prepare_data(use_smote=use_smote)
                
                if len(X_test) == 0 or len(y_test) == 0 or y_test.nunique() < 2:
                    print(f"Sem dados de teste suficientes para operação {operacao}.")
                    self.df = df_backup
                    continue
                
                # Treinar modelo para esta operação (temporariamente XGBoost para teste)
                self.model = XGBClassifier(
                    n_estimators=2000,
                    learning_rate=0.005,
                    max_depth=3,
                    min_child_weight=25,
                    scale_pos_weight=10,
                    colsample_bytree=0.4,
                    reg_lambda=200,
                    subsample=0.7
                )
                self.model.fit(X_train, y_train)
                
                # Fazer previsões no conjunto de teste
                y_proba = self.model.predict_proba(X_test)[:, 1]
                y_pred = (y_proba > 0.6).astype(int)
                
                # Coletar resultados
                all_y_true.extend(y_test.tolist())
                all_y_pred.extend(y_pred.tolist())
                all_y_proba.extend(y_proba.tolist())
                
                operacoes_com_teste += 1
                print(f"Operação {operacao}: {len(X_test)} amostras de teste")
                
            except Exception as e:
                print(f"Erro na avaliação da operação {operacao}: {e}")
            
            finally:
                self.df = df_backup
        
        if len(all_y_true) == 0:
            print("Nenhuma operação teve dados de teste suficientes para avaliação.")
            return
        
        print(f"\nTotal de operações avaliadas: {operacoes_com_teste}")
        print(f"Total de amostras de teste: {len(all_y_true)}")
        
        # Calcular métricas globais
        accuracy = accuracy_score(all_y_true, all_y_pred)
        precision = precision_score(all_y_true, all_y_pred, zero_division=0)
        recall = recall_score(all_y_true, all_y_pred, zero_division=0)
        f1 = f1_score(all_y_true, all_y_pred, zero_division=0)
        auc_roc = roc_auc_score(all_y_true, all_y_proba)
        
        print("\n" + "-"*60)
        print("MÉTRICAS GERAIS DO MODELO")
        print("-"*60)
        print(f"Acurácia: {accuracy:.4f}")
        print(f"Precisão: {precision:.4f}")
        print(f"Recall: {recall:.4f}")
        print(f"F1-Score: {f1:.4f}")
        print(f"AUC-ROC: {auc_roc:.4f}")
        
        print("\nRelatório de Classificação Detalhado:")
        print(classification_report(all_y_true, all_y_pred, digits=4, zero_division=0))
        
        # Plotar matriz de confusão
        if plot_confusion_matrix:
            self._plot_confusion_matrix(all_y_true, all_y_pred)
        
        return {
            'accuracy': accuracy,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'auc_roc': auc_roc,
            'y_true': all_y_true,
            'y_pred': all_y_pred,
            'y_proba': all_y_proba
        }

    def _plot_confusion_matrix(self, y_true, y_pred):
        """Plota a matriz de confusão usando matplotlib e seaborn"""
        if not HAS_PLOTTING_LIBS:
            print("Bibliotecas de plotagem não disponíveis. Pulando plot da matriz de confusão.")
            return
            
        cm = confusion_matrix(y_true, y_pred)
        
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', 
                   xticklabels=['Não Ausente', 'Ausente'],
                   yticklabels=['Não Ausente', 'Ausente'])
        plt.title('Matriz de Confusão - Modelo de Previsão de Absenteísmo')
        plt.ylabel('Valor Real')
        plt.xlabel('Valor Previsto')
        plt.tight_layout()
        
        # Salvar a figura
        plt.savefig('confusion_matrix.png', dpi=300, bbox_inches='tight')
        print("\nMatriz de confusão salva como 'confusion_matrix.png'")
        plt.show()

    def predict_absenteeism(self, codigo_cliente):
        """Gera previsões de probabilidade de absenteísmo para escalas futuras"""
        # Verificar se as features foram calculadas
        required_features = ['TARGET_MEAN_INDIVIDUAL', 'ROLLING_ABSENCES_7D', 'TARGET_MEAN_SETOR']
        missing = [f for f in required_features if f not in self.df.columns]
        if missing:
            raise ValueError(f"Features não calculadas. Execute feature_engineering() antes. Faltam: {missing}")

        reference_date = pd.to_datetime(self.final_date_ctrl)
        # Usar 5 dias antes como referência para dados "futuros"
        hoje = reference_date - timedelta(days=5)
        df_futuro = self.df[
            (self.df['DATA'] >= hoje) &
            (self.df['ScheduledWorktime'] > 0)
        ].copy()

        if df_futuro.empty:
            print("Nenhuma escala futura encontrada com tempo > 0.")
            return pd.DataFrame()

        # As novas features já foram calculadas em feature_engineering
        # Apenas garantir que todas as features necessárias estejam presentes
        for col in self.features:
            if col not in df_futuro.columns:
                print(f"Aviso: Feature {col} não encontrada. Preenchendo com 0.")
                df_futuro[col] = 0

        X_pred = df_futuro[self.features].copy()
        X_pred.fillna(0, inplace=True)
        df_futuro['PROBABILIDADE'] = self.model.predict_proba(X_pred)[:, 1]
        # Removendo PREVISAO_ABS, trabalhando apenas com probabilidade

        resultado = df_futuro[[
            'FpwIdHierarchyLevel1', 'CodeLevelServiceStructure3', 'DATA',
            'PROBABILIDADE'
        ]].rename(columns={'DATA': 'DATA_PREVISAO'})

        return resultado.sort_values(['DATA_PREVISAO', 'PROBABILIDADE'], ascending=[True, False])

    def _prepare_df_pred_insert(self, resultado):
        if resultado is None or resultado.empty:
            return pd.DataFrame(columns=[
                'FpwIdHierarchyLevel1', 'Data', 'Probabilidade_de_Ausencia', 'CodeLevelServiceStructure3'
            ])

        df_pred_insert = resultado.rename(columns={
            'FpwIdHierarchyLevel1': 'FpwIdHierarchyLevel1',
            'DATA_PREVISAO': 'Data',
            'PROBABILIDADE': 'Probabilidade_de_Ausencia',
            'CodeLevelServiceStructure3': 'CodeLevelServiceStructure3'
        })

        mandatory_columns = [
            'FpwIdHierarchyLevel1', 'Data',
            'Probabilidade_de_Ausencia', 'CodeLevelServiceStructure3'
        ]
        missing = [c for c in mandatory_columns if c not in df_pred_insert.columns]
        if missing:
            raise ValueError(f"Sem colunas esperadas nas predições: {missing}")

        df_pred_insert['Data'] = pd.to_datetime(df_pred_insert['Data'], errors='coerce')
        # Removendo filtro de Previsto_Ausencia, mantendo todas as previsões baseadas em probabilidade
        reference_date = pd.to_datetime(self.final_date_ctrl)
        df_pred_insert = df_pred_insert[
            (df_pred_insert['Data'] >= reference_date - timedelta(days=self.dias_filtro_previsao))
        ].copy()

        df_pred_insert['Data'] = df_pred_insert['Data'].dt.strftime('%Y-%m-%d')

        for col in df_pred_insert.select_dtypes(include=['object']).columns:
            df_pred_insert[col] = df_pred_insert[col].astype(str).str.slice(0, 255)

        return df_pred_insert

    def train_model_por_operacao(self, tune_hyperparams=False, use_smote=False):
        self._validate_required_columns(['CodeLevelServiceStructure3', 'TARGET', 'ScheduledWorktime', 'DATA', 'FpwIdHierarchyLevel1'])
        resultados = []
        operacoes = self.df['CodeLevelServiceStructure3'].dropna().unique().tolist()

        for operacao in operacoes:
            print(f"\nTreinando modelo para operação: {operacao}")
            df_op = self.df[self.df['CodeLevelServiceStructure3'] == operacao].copy()
            y_op = df_op['TARGET'].dropna()
            if y_op.nunique() < 2:
                print(f"Operação {operacao} não tem classes suficientes para treinamento. Pulando.")
                continue

            df_backup = self.df
            self.df = df_op.reset_index(drop=True)

            try:
                X_train, X_test, y_train, y_test = self.prepare_data(use_smote=use_smote)
                print(f"Treino={len(X_train)} | Teste={len(X_test)} | Classes treino={y_train.nunique()}")

                if tune_hyperparams:
                    self.tune_hyperparameters(use_smote=use_smote)
                else:
                    self.model = XGBClassifier(
                        n_estimators=2000,
                        learning_rate=0.005,
                        max_depth=3,
                        min_child_weight=25,
                        scale_pos_weight=10,
                        colsample_bytree=0.4,
                        reg_lambda=200,
                        subsample=0.7
                    )
                    self.model.fit(X_train, y_train)

                previsao_op = self.predict_absenteeism(codigo_cliente=operacao)
                if previsao_op is not None and not previsao_op.empty:
                    resultados.append(previsao_op)

            except Exception as e:
                print(f"Erro na operação {operacao}: {e}")

            finally:
                self.df = df_backup

        if resultados:
            all_results = pd.concat(resultados, ignore_index=True)
        else:
            all_results = pd.DataFrame(columns=[
                'FpwIdHierarchyLevel1', 'CodeLevelServiceStructure3', 'DATA_PREVISAO',
                'PROBABILIDADE'
            ])

        self.df_pred_insert = self._prepare_df_pred_insert(all_results)
        return self.df_pred_insert

    def display_data(self):
        """Exibe o DataFrame final de predições no console (limitado a 1000 linhas)"""
        if self.df_pred_insert is None or self.df_pred_insert.empty:
            print("Nenhuma previsão preparada para exibição.")
            return
        
        print("\n" + "="*100)
        print("DADOS DE PREVISÃO PRONTOS PARA INSERÇÃO")
        print("="*100)
        print(f"\nTotal de previsões: {len(self.df_pred_insert)}")
        print(f"\nColunas: {list(self.df_pred_insert.columns)}")
        print("\n" + "-"*100)
        
        df_display = self.df_pred_insert.head(1000)
        print(df_display.to_string(index=False))
        
        if len(self.df_pred_insert) > 1000:
            print(f"\n... ({len(self.df_pred_insert) - 1000} linhas omitidas)")
        
        print("-"*100 + "\n")
    
    def insert_data(self):
        """Insere os dados de predição no banco de dados na tabela especificada"""
        if self.df_pred_insert is None or self.df_pred_insert.empty:
            print("Nenhum dado para inserir.")
            return
        
        if not self.process_table:
            print("Tabela de processo não especificada. Pulando inserção.")
            return
        
        try:
            # TRUNCATE da tabela antes de inserir
            print(f"Truncando tabela {self.process_table}...")
            truncate_query = f"TRUNCATE TABLE {self.process_table}"
            self.cursor.execute(truncate_query)
            self.connection.commit()
            print(f"Tabela {self.process_table} truncada com sucesso.")
            
            # Selecionar colunas que serão inseridas (todas do df_pred_insert)
            columns = list(self.df_pred_insert.columns)
            placeholders = ', '.join(['?'] * len(columns))
            columns_str = ', '.join([f'[{col}]' for col in columns])  # Usar colchetes para nomes de colunas SQL Server
            
            insert_query = f"INSERT INTO {self.process_table} ({columns_str}) VALUES ({placeholders})"
            
            # Preparar os dados como lista de tuplas
            data = [tuple(row) for row in self.df_pred_insert.values]
            
            # Inserir dados
            self.cursor.executemany(insert_query, data)
            self.connection.commit()
            print(f"Inseridos {len(data)} registros na tabela {self.process_table}.")
            
            # Chamar procedure após insert bem-sucedido
            print("Executando procedure dbo.AtualizaAbsenteismoPredicao...")
            procedure_query = "EXEC dbo.AtualizaAbsenteismoPredicao @processKey = ?"
            self.cursor.execute(procedure_query, (self.process_key,))
            self.connection.commit()
            print("Procedure dbo.AtualizaAbsenteismoPredicao executada com sucesso.")
            
        except Exception as e:
            print(f"Erro ao inserir dados ou executar procedure: {e}")
            self.connection.rollback()
    
    def __del__(self):
        """Fecha a conexão quando o objeto é destruído"""
        if hasattr(self, 'cursor'):
            self.cursor.close()
        if hasattr(self, 'connection'):
            self.connection.close() 


