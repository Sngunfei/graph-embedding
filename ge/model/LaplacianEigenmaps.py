# -*- coding:utf-8 -*-

import networkx as nx
import numpy as np
from scipy.sparse import linalg, csr_matrix
import pandas as pd
from sklearn.manifold import SpectralEmbedding


class LaplacianEigenmaps:

    def __init__(self, graph, dim=16):
        self.graph = graph
        self.dim = dim

        self.n_nodes = graph.number_of_nodes()
        self.A = np.asarray(csr_matrix(nx.adjacency_matrix(graph)).toarray())
        self.nodes = list(graph.nodes())
        self.embeddings = {}


    def _sparse_process(self, threshold=None, percentile=None):
        """
        将邻接矩阵稀疏化
        :param threshold: 权重低于threshold的边将会被删掉
        :param percentile: 按照百分比删边
        :return:
        """
        del_edges = []
        edges = nx.edges(self.graph)
        if threshold:
            for edge in edges:
                u, v = edge
                if self.graph[u][v]['weight'] < threshold:
                    del_edges.append((u, v))
        elif percentile:
            _weights = []
            for edge in edges:
                u, v = edge
                # if one edge's weight very big, then would delete many valuable edges.
                #thres += 1.0 / n * (self.graph[u][v]['weight'] * percentile - thres)
                _weights.append(self.graph[u][v]['weight'])
            threshold = np.percentile(_weights, percentile * 100)

            for edge in edges:
                u, v = edge
                if self.graph[u][v]['weight'] < threshold:
                    del_edges.append((u, v))
        self.graph.remove_edges_from(del_edges)


    def spectralEmbedding(self):
        model = SpectralEmbedding(n_components=self.dim, affinity="precomputed", n_neighbors=int(self.n_nodes / 5))
        embeddings = np.asarray(model.fit_transform(self.A))
        for idx, node in enumerate(self.nodes):
            embedding = embeddings[idx, :]
            self.embeddings[node] = np.real(embedding)
        return self.embeddings


    def create_embedding(self, threshold=None, percentile=None):
        _n_edge = nx.number_of_edges(self.graph)
        if threshold or percentile:
            self._sparse_process(threshold, percentile)
        _n_edge1 = nx.number_of_edges(self.graph)
        print("n_edges: before:{}, after:{}\n".format(_n_edge, _n_edge1))
        L_sym = nx.normalized_laplacian_matrix(self.graph)
        w, v = linalg.eigs(L_sym, k=self.dim + 1, which='SM')
        X = v[:, 1:]
        p_d_p_t = np.dot(v, np.dot(np.diag(w), v.T))
        eig_err = np.linalg.norm(p_d_p_t - L_sym)
        print('Laplacian matrix recon. error (low rank): %f' % eig_err)

        for idx, node in enumerate(self.nodes):
            embedding = X[idx, :]
            self.embeddings[node] = np.real(embedding)
        return self.embeddings


    def save_embedding(self, filename):
        embeddings = np.array([embedding for embedding in self.embeddings.values()])
        df = pd.DataFrame(data=embeddings, index=self.nodes)
        df.to_csv(filename, mode='w+', encoding='utf8', header=[x for x in range(self.dim)])


    def get_embedding(self):
        return self._X


    def get_edge_weight(self, i, j):
        return np.exp(
            -np.power(np.linalg.norm(self._X[i, :] - self._X[j, :]), 2)
        )

    def get_reconstructed_adj(self, X=None, node_l=None):
        if X is not None:
            node_num = X.shape[0]
            self._X = X
        else:
            node_num = self.n_nodes
        adj_mtx_r = np.zeros((node_num, node_num))
        for v_i in range(node_num):
            for v_j in range(node_num):
                if v_i == v_j:
                    continue
                adj_mtx_r[v_i, v_j] = self.get_edge_weight(v_i, v_j)
        return adj_mtx_r
