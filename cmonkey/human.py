"""human.py - cMonkey human specific module

This file is part of cMonkey Python. Please see README and LICENSE for
more information and licensing details.
"""
import logging
import numpy
import scipy
import util
import thesaurus
import organism

SEARCH_DISTANCES = {'promoter': (0, 700), 'p3utr': (0, 831)}
SCAN_DISTANCES = {'promoter': (0, 700), 'p3utr': (0, 831)}


def genes_per_group_proportional(num_genes_total, num_per_group):
    """takes the total number of genes and a dictionary containing
    the number of members for each group and returns a dictionary that
    distributes the number of genes proportionally to each group"""
    result = {}
    num_group_elems = sum(num_per_group.values())
    groups = num_per_group.keys()
    for index in range(len(groups)):
        group = groups[index]
        if index == len(groups) - 1:
            result[group] = num_genes_total - sum(result.values())
        else:
            result[group] = int(float(num_genes_total) *
                                float(num_per_group[group]) /
                                float(num_group_elems))
    return result


def genes_per_group_nonproportional(num_genes_total, groups):
    """distributes the number of genes evenly to each group given"""
    result = {}
    partition = int(float(num_genes_total) / float(len(groups)))
    for index in range(len(groups)):
        if index == len(groups) - 1:
            result[groups[index]] = num_genes_total - sum(result.values())
        else:
            result[groups[index]] = partition
    return result


def select_probes(matrix, num_genes_total, column_groups, proportional=True):
    """select probes proportional, column_groups is a map from a group
    label to column indexes in the matrix"""
    def coeff_var(row_values):
        """computes the coefficient of variation"""
        sigma = util.r_stddev(row_values)
        mu = numpy.mean(row_values)
        return sigma / mu

    num_per_group = {group: len(indexes)
                     for group, indexes in column_groups.items()}
    if proportional:
        per_group = genes_per_group_proportional(num_genes_total,
                                                 num_per_group)
    else:
        per_group = genes_per_group_proportional(num_genes_total,
                                                 column_groups.keys())

    cvrows = []
    for group, col_indexes in column_groups.items():
        group_cvs = []
        for row in range(matrix.num_rows()):
            row_values = [matrix[row][col] for col in col_indexes]
            group_cvs.append(coeff_var(row_values))
        cvrows += [group_cvs.index(value)
                   for value in
                   sorted(group_cvs, reverse=True)][:per_group[group]]
    return sorted(list(set(cvrows)))


def intensities_to_ratios(matrix, controls, column_groups):
    """turn intensities into ratios
    Warning: input matrix is modified !!!"""
    control_indexes = [matrix.column_names().index(control)
                       for control in controls
                       if control in matrix.column_names()]
    for group_columns in column_groups.values():
        group_controls = [index for index in control_indexes
                          if index in group_columns]
        means = []
        for row in range(matrix.num_rows()):
            values = [float(matrix[row][col]) for col in group_controls]
            means.append(sum(values) / float(len(values)))

        for col in group_columns:
            for row in range(matrix.num_rows()):
                matrix[row][col] /= means[row]

        center_scale_filter(matrix, group_columns, group_controls)
    return matrix


def center_scale_filter(matrix, group_columns, group_controls):
    """center the values of each row around their median and scale
    by their standard deviation. This is a specialized version"""
    centers = [scipy.median([matrix[row][col]
                             for col in group_controls])
               for row in range(matrix.num_rows())]
    scale_factors = [util.r_stddev([matrix[row][col]
                                    for col in group_columns])
                     for row in range(matrix.num_rows())]
    for row in range(matrix.num_rows()):
        for col in group_columns:
            matrix[row][col] -= centers[row]
            matrix[row][col] /= scale_factors[row]
    return matrix


##################
# Organism interface

class Human(organism.OrganismBase):
    """Implementation of a human organism"""

    def __init__(self, prom_seq_filename, p3utr_seq_filename,
                 thesaurus_filename, nw_factories,
                 search_distances=SEARCH_DISTANCES,
                 scan_distances=SCAN_DISTANCES):
        """Creates the organism"""
        organism.OrganismBase.__init__(self, 'hsa', nw_factories)
        self.__prom_seq_filename = prom_seq_filename
        self.__p3utr_seq_filename = p3utr_seq_filename
        self.__thesaurus_filename = thesaurus_filename
        self.__search_distances = search_distances
        self.__scan_distances = scan_distances

        # lazy-loaded values
        self.__synonyms = None
        self.__p3utr_seqs = None
        self.__prom_seqs = None

    def species(self):
        """Retrieves the species of this object"""
        return 'hsa'

    def is_eukaryote(self):
        """Determines whether this object is an eukaryote"""
        return False

    def sequences_for_genes_search(self, gene_aliases, seqtype):
        """retrieve the sequences for the specified"""
        distance = self.__search_distances[seqtype]
        if seqtype == 'p3utr':
            return self.__get_p3utr_seqs(gene_aliases, distance)
        else:
            return self.__get_promoter_seqs(gene_aliases, distance)

    def sequences_for_genes_scan(self, gene_aliases, seqtype):
        """retrieve the sequences for the specified"""
        distance = self.__scan_distances[seqtype]
        if seqtype == 'p3utr':
            return self.__get_p3utr_seqs(gene_aliases, distance)
        else:
            return self.__get_promoter_seqs(gene_aliases, distance)

    def __get_p3utr_seqs(self, gene_aliases, distance):
        """Retrieves genomic sequences from the 3" UTR set"""
        print "GET_P3UTR SEQS, distance: ", distance
        if self.__p3utr_seqs == None:
            dfile = util.DelimitedFile.read(self.__p3utr_seq_filename, sep=',')
            self.__p3utr_seqs = {}
            for line in dfile.lines():
                self.__p3utr_seqs[line[0].upper()] = line[1]
        result = {}
        for alias in gene_aliases:
            if alias in self.thesaurus():
                gene = self.thesaurus()[alias]
                if gene in self.__p3utr_seqs:
                    result[gene] = self.__p3utr_seqs[gene]
                else:
                    #logging.warn("Gene '%s' not found in 3' UTRs", gene)
                    pass
            else:
                #logging.warn("Alias '%s' not in thesaurus !", alias)
                pass
        return result

    def __get_promoter_seqs(self, gene_aliases, distance):
        """Retrieves genomic sequences from the promoter set"""
        logging.info("GET PROMOTER SEQS, # GENES: %d", len(gene_aliases))
        if self.__prom_seqs == None:
            dfile = util.DelimitedFile.read(self.__prom_seq_filename, sep=',')
            self.__prom_seqs = {}
            for line in dfile.lines():
                self.__prom_seqs[line[0].upper()] = line[1]
        result = {}
        for alias in gene_aliases:
            if alias in self.thesaurus():
                gene = self.thesaurus()[alias]
                if gene in self.__prom_seqs:
                    seq = self.__prom_seqs[gene]
                    # result[gene] = st.subsequence(seq, distance[0],
                    #                               distance[1])
                    result[gene] = seq
                else:
                    #logging.warn("Gene '%s' not found in promoter seqs", gene)
                    pass
            else:
                #logging.warn("Alias '%s' not in thesaurus !", alias)
                pass
        logging.info("sequences all retrieved")
        return result

    def thesaurus(self):
        """Reads the synonyms from the provided CSV file"""
        if not self.__synonyms:
            self.__synonyms = thesaurus.create_from_delimited_file2(
                self.__thesaurus_filename)
        return self.__synonyms