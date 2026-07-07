import os
from dotenv import load_dotenv 
from typing import List, Optional
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client

# <-- 2. Carregue o arquivo .env ANTES de ler as chaves -->
load_dotenv()

app = FastAPI(title="ClickArt Gestão API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# <-- 3. Puxe as variáveis com os.getenv (como estava na versão original) -->
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Proteção extra: garantir que o servidor avise se esquecermos de criar o .env
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("As credenciais do Supabase não foram encontradas no arquivo .env!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# ==========================================
# SCHEMAS (Modelos de Validação - Pydantic)
# ==========================================
class ItemVendaInput(BaseModel):
    produto_id: str
    quantidade: int
    preco_unitario: float

class NovaVendaInput(BaseModel):
    itens: List[ItemVendaInput]

class ProdutoInput(BaseModel):
    sku: str
    nome: str
    categoria: str
    preco_venda: float
    quantidade_atual: int
    estoque_minimo: Optional[int] = 5
    imagem_url: Optional[str] = None

class ProdutoUpdateInput(BaseModel):
    sku: Optional[str] = None
    nome: Optional[str] = None
    categoria: Optional[str] = None
    preco_venda: Optional[float] = None
    quantidade_atual: Optional[int] = None
    estoque_minimo: Optional[int] = None
    imagem_url: Optional[str] = None


# ==========================================
# ROTAS: DASHBOARD (HOME)
# ==========================================
from datetime import datetime

@app.get("/dashboard", status_code=status.HTTP_200_OK)
def obter_dados_dashboard():
    try:
        # 1. Métricas Básicas (Mantido)
        vendas_res = supabase.table("vendas").select("valor_total").execute()
        vendas_totais = sum([float(v["valor_total"]) for v in vendas_res.data])

        produtos_res = supabase.table("produtos").select("quantidade_atual", "preco_venda", "estoque_minimo", "nome", "sku").execute()
        valor_estoque = sum([p["quantidade_atual"] * p["preco_venda"] for p in produtos_res.data])
        produtos_baixo_estoque = [p for p in produtos_res.data if p["quantidade_atual"] <= p["estoque_minimo"]]

        financas_res = supabase.table("transacoes_financeiras").select("tipo", "valor").execute()
        fluxo_caixa = sum([float(t["valor"]) if t["tipo"] == "entrada" else -float(t["valor"]) for t in financas_res.data])

        # 2. Gráfico (Versão Simplificada e Segura)
        vendas_detalhes = supabase.table("vendas").select("valor_total, data_venda").execute()
        
        # Inicializa lista com 12 zeros
        dados_grafico = [0.0] * 12
        meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        
        for v in vendas_detalhes.data:
            # Tenta converter data com segurança
            try:
                # Remove o 'T' ou 'Z' se necessário e converte
                data_str = v["data_venda"].split('T')[0] 
                data = datetime.strptime(data_str, "%Y-%m-%d")
                mes_idx = data.month - 1
                dados_grafico[mes_idx] += float(v["valor_total"])
            except:
                continue

        return {
            "metricas": { "vendas_totais": vendas_totais, "valor_estoque": valor_estoque, "fluxo_caixa": fluxo_caixa },
            "produtos_baixo_estoque": produtos_baixo_estoque,
            "grafico": { "labels": meses, "dados": dados_grafico }
        }
        
    except Exception as e:
        print(f"Erro detalhado no dashboard: {e}") # Isso aparece no terminal!
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# ROTAS: VENDAS (PDV)
# ==========================================
@app.post("/vendas", status_code=status.HTTP_201_CREATED)
def registrar_venda(venda_input: NovaVendaInput):
    try:
        itens_para_processar = []
        valor_total_venda = 0.0

        # Passo 1: Validar a disponibilidade de TODOS os itens antes de alterar o banco
        for item in venda_input.itens:
            produto_res = supabase.table("produtos").select("nome", "quantidade_atual").eq("id", item.produto_id).single().execute()
            
            if not produto_res.data:
                raise HTTPException(status_code=404, detail=f"Produto ID {item.produto_id} não encontrado.")
            
            produto = produto_res.data
            if produto["quantidade_atual"] < item.quantidade:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Atenção: Quantidade excede o estoque disponível para {produto['nome']} ({produto['quantidade_atual']} disponíveis)!"
                )
            
            valor_total_venda += item.quantidade * item.preco_unitario
            itens_para_processar.append((item, produto["quantidade_atual"]))

        # Passo 2: Criar o cabeçalho da venda
        nova_venda_res = supabase.table("vendas").insert({"valor_total": valor_total_venda}).execute()
        venda_id = nova_venda_res.data[0]["id"]

        # Passo 3: Processar os itens, atualizar o estoque e salvar o histórico
        for item, qtd_atual in itens_para_processar:
            # Registrar item da venda
            supabase.table("itens_venda").insert({
                "venda_id": venda_id,
                "produto_id": item.produto_id,
                "quantidade": item.quantidade,
                "preco_unitario": item.preco_unitario
            }).execute()

            # Atualizar estoque (baixa automática)
            nova_qtd = qtd_atual - item.quantidade
            supabase.table("produtos").update({"quantidade_atual": nova_qtd}).eq("id", item.produto_id).execute()

        # Passo 4: Gerar automaticamente o lançamento de Entrada no Fluxo de Caixa
        supabase.table("transacoes_financeiras").insert({
            "tipo": "entrada",
            "categoria": "Venda",
            "valor": valor_total_venda,
            "descricao": f"Recebimento automático da venda {venda_id[:8]}"
        }).execute()

        return {"status": "sucesso", "venda_id": venda_id, "valor_total": valor_total_venda}

    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno ao registrar venda: {str(e)}")


# ==========================================
# ROTAS: PRODUTOS (CRUD DO INVENTÁRIO)
# ==========================================
@app.get("/produtos", status_code=status.HTTP_200_OK)
def listar_produtos(busca: Optional[str] = None, categoria: Optional[str] = None):
    try:
        query = supabase.table("produtos").select("*")
        
        if busca:
            query = query.or_(f"nome.ilike.%{busca}%,sku.ilike.%{busca}%")
        
        if categoria:
            query = query.eq("categoria", categoria)
            
        resultado = query.execute()
        return resultado.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao listar produtos: {str(e)}")


@app.get("/produtos/{produto_id}", status_code=status.HTTP_200_OK)
def obter_produto(produto_id: str):
    try:
        resultado = supabase.table("produtos").select("*").eq("id", produto_id).single().execute()
        if not resultado.data:
            raise HTTPException(status_code=404, detail="Produto não encontrado.")
        return resultado.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar produto: {str(e)}")


@app.post("/produtos", status_code=status.HTTP_201_CREATED)
def criar_produto(produto: ProdutoInput):
    try:
        resultado = supabase.table("produtos").insert(produto.model_dump()).execute()
        return {"status": "sucesso", "dados": resultado.data[0]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao cadastrar produto: {str(e)}")


@app.put("/produtos/{produto_id}", status_code=status.HTTP_200_OK)
def atualizar_produto(produto_id: str, produto_dados: ProdutoUpdateInput):
    try:
        dados_filtrados = {k: v for k, v in produto_dados.model_dump().items() if v is not None}
        
        if not dados_filtrados:
            raise HTTPException(status_code=400, detail="Nenhum dado informado para atualização.")
            
        resultado = supabase.table("produtos").update(dados_filtrados).eq("id", produto_id).execute()
        
        if not resultado.data:
            raise HTTPException(status_code=404, detail="Produto não encontrado para atualização.")
            
        return {"status": "sucesso", "dados": resultado.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao atualizar produto: {str(e)}")


@app.delete("/produtos/{produto_id}", status_code=status.HTTP_200_OK)
def deletar_produto(produto_id: str):
    try:
        resultado = supabase.table("produtos").delete().eq("id", produto_id).execute()
        if not resultado.data:
            raise HTTPException(status_code=404, detail="Produto não encontrado ou já removido.")
        return {"status": "sucesso", "mensagem": "Produto removido com sucesso."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao remover produto: {str(e)}")


# ==========================================
# ROTAS: FINANCEIRO (HISTÓRICO E FILTROS)
# ==========================================
@app.get("/financeiro", status_code=status.HTTP_200_OK)
def listar_transacoes(
    tipo: Optional[str] = None, 
    categoria: Optional[str] = None, 
    data_inicio: Optional[str] = None, 
    data_fim: Optional[str] = None
):
    try:
        query = supabase.table("transacoes_financeiras").select("*").order("data_transacao", desc=True)
        
        if tipo:
            if tipo not in ['entrada', 'saida']:
                raise HTTPException(status_code=400, detail="O tipo deve ser 'entrada' ou 'saida'.")
            query = query.eq("tipo", tipo)
            
        if categoria:
            query = query.ilike("categoria", f"%{categoria}%")
            
        if data_inicio:
            query = query.gte("data_transacao", data_inicio)
        if data_fim:
            query = query.lte("data_transacao", f"{data_fim}T23:59:59")
            
        resultado = query.execute()
        
        total_entradas = sum([float(t["valor"]) for t in resultado.data if t["tipo"] == "entrada"])
        total_saidas = sum([float(t["valor"]) for t in resultado.data if t["tipo"] == "saida"])
        saldo_periodo = total_entradas - total_saidas
        
        return {
            "resumo_periodo": {
                "total_entradas": total_entradas,
                "total_saidas": total_saidas,
                "saldo_periodo": saldo_periodo,
                "total_registros": len(resultado.data)
            },
            "transacoes": resultado.data
        }
    except HTTPException as http_err:
        raise http_err
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar histórico financeiro: {str(e)}")