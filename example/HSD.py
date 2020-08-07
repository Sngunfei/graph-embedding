# -*- coding:utf-8 -*-

"""
HSD
"""

import logging
import datetime
import os
import sys

curPath = os.path.abspath(os.path.dirname(__file__))
rootPath = os.path.split(curPath)[0]
sys.path.append(rootPath)
from ge.tools.dataloader import load_data, load_data_from_distance
from ge.tools.robustness import add_noise
from ge.tools.visualize import plot_embeddings
from ge.tools import rw
from ge.tools import util
from example.params_parser import  HSDParameterParser, tab_printer
from ge.model.HSD import HSD
from ge.model.LaplacianEigenmaps import LaplacianEigenmaps
from ge.model.LocallyLinearEmbedding import LocallyLinearEmbedding
from ge.evaluate.evaluate import KNN_evaluate, LR_evaluate, cluster_evaluate
from sklearn.manifold import TSNE
import numpy as np
import networkx as nx
import time
import warnings
from tqdm import tqdm
warnings.filterwarnings("ignore")

# todo
def get_file_path() -> dict:
    # 根据参数组装各个中间状态的存储路径信息
    return {}

def run(hsd, label_dict: dict, n_class: int, params):
    if params.graph == "bio_dmela":
        scale = util.recommend_scale(hsd.wavelet.e)
    else:
        scale = 1
    params.scale = scale
    hsd.scale = scale
    if str.lower(params.multi_scales) == "yes":  # 多尺度
        #hsd.initialize(multi=True)
        # 结构距离存储路径
        dist_file_path = "../distance/{}/HSD_multi_{}_hop{}.edgelist".format(
            hsd.graph_name, params.metric, params.hop)
        # tsne得到的2维向量存储路径
        tsne_vect_path = "../tsne_vectors/{}/HSD_multi_{}_hop{}_tsne{}.csv".format(
            hsd.graph_name, hsd.metric, hsd.hop, params.tsne)
        # tsne得到的图片存储路径
        tsne_figure_path = "../tsne_figures/{}/HSD_multi_{}_hop{}_tsne{}.png".format(
            hsd.graph_name, hsd.metric, hsd.hop, params.tsne)
    else:  # 单尺度
        #hsd.initialize(multi=False)
        dist_file_path = "../distance/{}/HSD_{}_scale{}_hop{}.edgelist".format(
            hsd.graph_name, params.metric, params.scale, params.hop)
        tsne_vect_path = "../tsne_vectors/{}/HSD_{}_scale{}_hop{}_tsne{}.csv".format(
            hsd.graph_name, hsd.metric, hsd.scale, hsd.hop, params.tsne)
        tsne_figure_path = "../tsne_figures/{}/HSD_{}_scale{}_hop{}_tsne{}.png".format(
            hsd.graph_name, hsd.metric, hsd.scale, hsd.hop, params.tsne)

    # 直接读取之前已经计算好的距离
    if params.reuse == "yes" and os.path.exists(path=dist_file_path):
        dist_info = rw.read_distance(dist_file_path, hsd.n_nodes)
        dist_mat = np.zeros((hsd.n_nodes, hsd.n_nodes), dtype=np.float)
        for idx, node in enumerate(hsd.nodes):
            node = int(node)
            for idx2 in range(idx + 1, hsd.n_nodes):
                node2 = int(hsd.nodes[idx2])
                dist_mat[idx, idx2] = dist_mat[idx2, idx] = dist_info[node, node2]
        logging.info("Reuse distance information.")
    else:
        if str.lower(params.multi_scales) == "no":
            scale = util.recommend_scale(hsd.wavelet.e)
            print("scale: ", scale)
            hsd.scale = scale
            # dist_mat = hsd.parallel_calculate_distance()
            dist_mat = hsd.calculate_structural_distance()
        elif str.lower(params.multi_scales) == "yes":
            #hsd.calculate_multi_scales_coeff_sum(n_scales=200)
            dist_mat = hsd.single_multi_scales_wavelet(n_scales=200, reuse=True)
            #dist_mat = hsd.parallel_multi_scales_wavelet(n_scales=200, reuse=False)
        else:
            raise ValueError("Multi-scales mode should be yes/no.")

    # 过滤，只保留重要的边，缩小重建图的规模
    util.filter_distance_matrix(dist_mat, nodes=hsd.nodes, save_path=dist_file_path, ratio=0.2)

    result_args = {
        "date": datetime.datetime.now() - datetime.timedelta(hours=8),
        "multi-scales": params.multi_scales,
        "scale": hsd.scale,
        "hop": hsd.hop,
        "metric": hsd.metric,
        "dim": params.dim,
        "sparse": params.sparse
    }

    labels = [label_dict[node] for node in hsd.nodes]

    if hsd.graph_name in ["varied_graph"]:
        h, c, v, s = cluster_evaluate(dist_mat, labels, n_class, metric="precomputed")
        res = KNN_evaluate(dist_mat, labels, metric="precomputed", cv=10, n_neighbor=4)
        tsne_res = TSNE(n_components=2, metric="precomputed", learning_rate=50.0, n_iter=2000,
                        perplexity=params.tsne, random_state=params.random).fit_transform(dist_mat)

        rw.save_vectors(hsd.nodes, vectors=tsne_res, path=tsne_vect_path)
        plot_embeddings(hsd.nodes, tsne_res, labels=labels, n_class=n_class, save_path=tsne_figure_path)
        return h, c, v, s, res['accuracy'], res['macro f1'], res['micro f1']

    if hsd.graph_name not in ["mkarate", "barbell"]:
        knn_res = KNN_evaluate(dist_mat, labels, metric="precomputed", cv=params.cv,
                               n_neighbor=params.neighbors)
        knn_res.update(result_args)
        rw.save_results(knn_res, "../results/knn/HSD_{}.txt".format(hsd.graph_name))

    tsne_res = TSNE(n_components=2, metric="precomputed", learning_rate=5.0, n_iter=2000,
                    perplexity=params.tsne, random_state=params.random).fit_transform(dist_mat)

    rw.save_vectors(hsd.nodes, vectors=tsne_res, path=tsne_vect_path)
    plot_embeddings(hsd.nodes, tsne_res, labels=labels, n_class=n_class, save_path=tsne_figure_path)

    method = str.lower(params.embedding_method)
    if method in ['le', 'lle']:
        print(f"start graph embedding, method: {method}")
        new_graph, _, _, = load_data_from_distance(hsd.graph_name, label_name=None,
                                                   metric=params.metric, hop=hsd.hop, scale=hsd.scale,
                                                   multi=params.multi_scales, directed=False)
        graph_sparse = util.sparse_graph(new_graph, percentile=params.sparse)
        test_graph(graph_sparse)
        if method == "le":
            LE = LaplacianEigenmaps(graph_sparse, n_neighbors=params.neighbors, dim=params.dim)
            embeddings_dict = LE.create_embedding()
        else:
            LLE = LocallyLinearEmbedding(graph_sparse, n_neighbors=params.neighbors, dim=params.dim)
            embeddings_dict = LLE.sklearn_lle(random_state=params.random)

        embeddings = []
        labels = []
        for idx, node in enumerate(hsd.nodes):
            embeddings.append(embeddings_dict[node])
            labels.append(label_dict[node])

        rw.save_vectors(nodes=hsd.nodes, vectors=embeddings,
                        path="../embeddings/{}_{}_{}.csv".format(method, hsd.graph_name, hsd.metric))

        if hsd.graph_name not in ['barbell', 'mkarate']:
            lr_res = LR_evaluate(embeddings, labels, cv=params.cv, test_size=params.test_size,
                                 random_state=params.random)
            lr_res.update(result_args)
            rw.save_results(lr_res, "../results/lr/HSD{}_{}.txt".format(str.upper(method), graph_name))

            knn_res = KNN_evaluate(embeddings, labels, cv=params.cv, n_neighbor=params.neighbors,
                                   random_state=params.random)
            knn_res.update(result_args)
            rw.save_results(knn_res, "../results/knn/HSD{}_{}.txt".format(str.upper(method), graph_name))

        tsne_res = TSNE(n_components=2, metric="euclidean", learning_rate=50.0, n_iter=2000,
                        perplexity=params.tsne, random_state=params.random).fit_transform(embeddings)

        rw.save_vectors(hsd.nodes, tsne_res, path=tsne_vect_path)
        plot_embeddings(hsd.nodes, tsne_res, labels, n_class, save_path=tsne_figure_path)

def test_graph(sparsed_graph: nx.Graph):
    """
    发现sparse处理过的图，效果会很差，专门开个函数测一下相关属性
    :return:
    """
    print("Number of edges: {}".format(nx.number_of_edges(sparsed_graph)))
    print("Number of nodes: {}".format(nx.number_of_nodes(sparsed_graph)))
    print("Number of nodes without neighbor: {}".format(nx.number_of_isolates(sparsed_graph)))
    print("Number of component: {}".format(nx.number_connected_components(sparsed_graph)))

    average_degree = sum([d for _, d in nx.degree(sparsed_graph)]) / nx.number_of_nodes(sparsed_graph)
    print("Average degree: {}".format(average_degree))

def exec(graph, labels, n_class, mode, perp=10):
    """

    :param graph:
    :param labels: dict{label_name: label_dict}
    :param mode:
    :param n_class:
    :return:
    """
    model = HSD(graph, "varied_graph", scale=1, hop=2, metric=None, n_workers=3)
    if mode == 0:
        # 单尺度
        model.initialize(multi=False)
        dist_mat = model.parallel_calculate_distance(metric="wasserstein")
    else:
        # 多尺度
        model.initialize(multi=True)
        dist_mat = model.parallel_multi_scales_wavelet(n_scales=100, metric="hellinger", reuse=False)

    tsne_res = TSNE(n_components=2, metric="precomputed", learning_rate=50.0, n_iter=2000,
                    perplexity=perp, random_state=42).fit_transform(dist_mat)

    res = dict()
    for name, label_dict in labels.items():
        _labels = [label_dict[node] for node in model.nodes]
        h, c, v, s = cluster_evaluate(dist_mat, _labels, n_class, metric="precomputed")
        _res = KNN_evaluate(dist_mat, _labels, metric="precomputed", cv=5, n_neighbor=4)
        res[name] = [h, c, v, s, _res['accuracy'], _res['macro f1'], _res['micro f1']]
        plot_embeddings(model.nodes, tsne_res, labels=_labels, n_class=n_class, save_path=
        f"E:\workspace\py\graph-embedding\\figures\HSD-{mode}-{name}-{perp}.png")

    return res

if __name__ == '__main__':
    start = time.time()
    params = HSDParameterParser()
    params.graph = "bio_dmela"
    tab_printer(params)
    graph_name = params.graph
    graph, label_dict, n_class = load_data(graph_name, label_name=None)
    model = HSD(graph, graph_name, scale=params.scale, hop=params.hop,
                metric=params.metric, n_workers=params.workers)
    #model.calculate_multi_scales_coeff_sum(n_scales=200)
    run(model, label_dict, n_class, params)
    #scale = util.recommend_scale(model.wavelet.e)
    #print(f"scale: {scale}")
    #params.scale = scale
    #with open(f"../coeff/{graph_name}/scale{scale}.csv", mode="w+", encoding="utf-8") as fout:
    #    for node_idx, node in tqdm(enumerate(model.wavelet.nodes)):
     #       coeff = model.wavelet._calculate_node_coefficients(node_idx, scale)
     #       fout.write(f"{node}: {','.join(list(map(str, coeff)))}\n")
     #       fout.flush()
    #model.calculate_multi_scales_coeff_sum(100)
    #run(model, label_dict, n_class, params)
    params = HSDParameterParser()
    graph_name = "bio_grid_human"
    params.graph = graph_name
    graph, label_dict, n_class = load_data(graph_name, label_name=None)
    model = HSD(graph, graph_name, scale=1.0, hop=params.hop,
                metric=params.metric, n_workers=params.workers)
    model.calculate_multi_scales_coeff_sum(n_scales=200)
    run(model, label_dict, n_class, params)
    print("time: ", time.time() - start)
