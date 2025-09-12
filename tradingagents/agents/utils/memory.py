import chromadb
from chromadb.config import Settings
import requests
import os


class FinancialSituationMemory:
    def __init__(self, name, config):
        # 根据不同的模型提供商设置embedding模型
        if config["backend_url"] == "http://localhost:11434/v1":
            self.embedding = "nomic-embed-text"
        elif "dashscope.aliyuncs.com" in config["backend_url"]:
            self.embedding = "text-embedding-v2"  # 通义千问embedding模型
        elif "baidu" in config["backend_url"]:
            self.embedding = "bge-large-zh-v1.5"  # 文心一言embedding模型
        else:
            self.embedding = "text-embedding-3-small"  # 默认OpenAI模型
            
        self.config = config
        self.chroma_client = chromadb.Client(Settings(allow_reset=True))
        self.situation_collection = self.chroma_client.create_collection(name=name)

    def get_embedding(self, text):
        """Get embedding for a text using the configured model"""
        
        # 根据不同的模型提供商调用不同的API
        if "dashscope.aliyuncs.com" in self.config["backend_url"]:
            return self._get_qwen_embedding(text)
        elif "baidu" in self.config["backend_url"]:
            return self._get_ernie_embedding(text)
        else:
            # 对于其他模型，使用简化的embedding（返回固定向量）
            return self._get_simple_embedding(text)
    
    def _get_qwen_embedding(self, text):
        """获取通义千问embedding"""
        try:
            headers = {
                "Authorization": f"Bearer {os.getenv('DASHSCOPE_API_KEY')}",
                "Content-Type": "application/json"
            }
            
            data = {
                "model": self.embedding,
                "input": text
            }
            
            response = requests.post(
                f"{self.config['backend_url'].replace('/chat/completions', '/embeddings')}",
                headers=headers,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result["data"][0]["embedding"]
        except Exception as e:
            print(f"⚠️ 通义千问embedding调用失败: {e}")
            return self._get_simple_embedding(text)
    
    def _get_ernie_embedding(self, text):
        """获取文心一言embedding"""
        try:
            # 文心一言的embedding API调用
            # 这里使用简化的实现
            return self._get_simple_embedding(text)
        except Exception as e:
            print(f"⚠️ 文心一言embedding调用失败: {e}")
            return self._get_simple_embedding(text)
    
    def _get_simple_embedding(self, text):
        """简化的embedding实现（返回固定长度的向量）"""
        # 使用文本的hash值生成固定长度的向量
        import hashlib
        hash_obj = hashlib.md5(text.encode('utf-8'))
        hash_bytes = hash_obj.digest()
        
        # 生成1536维的向量（与OpenAI embedding维度相同）
        embedding = []
        for i in range(1536):
            byte_index = i % len(hash_bytes)
            embedding.append((hash_bytes[byte_index] - 128) / 128.0)
        
        return embedding

    def add_situations(self, situations_and_advice):
        """Add financial situations and their corresponding advice. Parameter is a list of tuples (situation, rec)"""

        situations = []
        advice = []
        ids = []
        embeddings = []

        offset = self.situation_collection.count()

        for i, (situation, recommendation) in enumerate(situations_and_advice):
            situations.append(situation)
            advice.append(recommendation)
            ids.append(str(offset + i))
            embeddings.append(self.get_embedding(situation))

        self.situation_collection.add(
            documents=situations,
            metadatas=[{"recommendation": rec} for rec in advice],
            embeddings=embeddings,
            ids=ids,
        )

    def get_memories(self, current_situation, n_matches=1):
        """Find matching recommendations using OpenAI embeddings"""
        query_embedding = self.get_embedding(current_situation)

        results = self.situation_collection.query(
            query_embeddings=[query_embedding],
            n_results=n_matches,
            include=["metadatas", "documents", "distances"],
        )

        matched_results = []
        for i in range(len(results["documents"][0])):
            matched_results.append(
                {
                    "matched_situation": results["documents"][0][i],
                    "recommendation": results["metadatas"][0][i]["recommendation"],
                    "similarity_score": 1 - results["distances"][0][i],
                }
            )

        return matched_results


if __name__ == "__main__":
    # Example usage
    matcher = FinancialSituationMemory()

    # Example data
    example_data = [
        (
            "High inflation rate with rising interest rates and declining consumer spending",
            "Consider defensive sectors like consumer staples and utilities. Review fixed-income portfolio duration.",
        ),
        (
            "Tech sector showing high volatility with increasing institutional selling pressure",
            "Reduce exposure to high-growth tech stocks. Look for value opportunities in established tech companies with strong cash flows.",
        ),
        (
            "Strong dollar affecting emerging markets with increasing forex volatility",
            "Hedge currency exposure in international positions. Consider reducing allocation to emerging market debt.",
        ),
        (
            "Market showing signs of sector rotation with rising yields",
            "Rebalance portfolio to maintain target allocations. Consider increasing exposure to sectors benefiting from higher rates.",
        ),
    ]

    # Add the example situations and recommendations
    matcher.add_situations(example_data)

    # Example query
    current_situation = """
    Market showing increased volatility in tech sector, with institutional investors 
    reducing positions and rising interest rates affecting growth stock valuations
    """

    try:
        recommendations = matcher.get_memories(current_situation, n_matches=2)

        for i, rec in enumerate(recommendations, 1):
            print(f"\nMatch {i}:")
            print(f"Similarity Score: {rec['similarity_score']:.2f}")
            print(f"Matched Situation: {rec['matched_situation']}")
            print(f"Recommendation: {rec['recommendation']}")

    except Exception as e:
        print(f"Error during recommendation: {str(e)}")
