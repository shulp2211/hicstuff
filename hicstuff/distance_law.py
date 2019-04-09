#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import numpy as np
import sys
import matplotlib.pyplot as plt
import matplotlib
import warnings
from scipy import ndimage
from matplotlib import cm
import hicstuff.io as hio
import pandas as pd
import os as os
import csv as csv

matplotlib.use("Agg")


def export_distance_law(xs, ps, names, out_dir=None):
    """ Export the xs and ps from two list of numpy.ndarrays to a table in txt 
    file with three coulumns separated by a tabulation. The first column
    contains the xs, the second the ps and the third the name of the arm or 
    chromosome. The file is createin the directory given by outdir or the 
    current directory if no directory given.
    
    Parameters
    ----------
    xs : list of numpy.ndarray
        The list of the logbins of each ps.
    ps : list of numpy.ndarray
        The list of ps.
    names : list of string
        List containing the names of the chromosomes/arms/conditions of the ps
        values given.
    out_dir : str or None
        Path where output files should be written. Current directory by 
        default.
    
    Return
    ------
    txt file:
         File with three coulumns separated by a tabulation. The first column
         contains the xs, the second the ps and the third the name of the arm  
         or chromosome. The file is createin the directory given by outdir or 
         the current directory if no directory given. 
    """
    # Give the current directory as out_dir if no out_dir is given.
    if out_dir is None:
        out_dir = os.getcwd()
    # Sanity check: as many chromosomes/arms as ps
    if len(xs) != len(names):
        sys.stderr.write("ERROR: Number of chromosomes/arms and number of ps differ.")
        sys.exit(1)
    # Create the file and write it
    f = open(out_dir, "w")
    for i in range(len(xs)):
        for j in range(len(xs[i])):
            ligne = str(xs[i][j]) + "\t" + str(ps[i][j]) + "\t" + names[i] + "\n"
            f.write(ligne)
    f.close()


def import_distance_law(distance_law_file):
    """ Import the table create by export_distance_law and return the list of 
    xs and ps in the order of the chromosomes.
    
    Parameters
    ----------
    distance_law_file : string
        Path to the file containing three columns : the xs, the ps, and the 
        chromosome/arm name.
    
    Return
    ------
    list of numpy.ndarray :
        The start coordinate of each bin one array per chromosome or arm.
    list of numpy.ndarray :
        The distance law probabilities corresponding of the bins of the 
        previous list.
    list of numpy.ndarray :
        The names of the arms/chromosomes corresponding to the previous 
        list.
    """
    file = pd.read_csv(distance_law_file, sep="\t", header=0)
    names = np.unique(file.iloc[:, 2])
    xs = [None] * len(names)
    ps = [None] * len(names)
    labels = [None] * len(names)
    for i in range(len(names)):
        subfile = file[file.iloc[:, 2] == names[i]]
        xs[i] = np.array(subfile.iloc[:, 0])
        ps[i] = np.array(subfile.iloc[:, 1])
        labels[i] = np.array(subfile.iloc[:, 2])
    return xs, ps, labels


def get_chr_segment_bins_index(fragments, centro_file=None):
    """Get the index positions of the bins of different chromosomes, or arms if
    the centromers position have been given from the fragments file made by 
    hicstuff.
    
    Parameters
    ----------
    fragments : pandas.DataFrame
        Table containing in the first coulum the ID of the fragment, in the 
        second the names of the chromosome in the third and fourth the start 
        position and the end position of the fragment. The file have no header.
        (File like the 'fragments_list.txt' from hicstuff)
    centro_file : None or str
        None or path to a file with the genomic positions of the centromers 
        sorted as the chromosomes separated by a space. The file have only one 
        line.
        
    Returns
    -------
    list of floats :
        The start indices of chromosomes/arms to compute the distance law on 
        each chromosome/arm separately.
    """
    # Get bins where chromosomes start
    chr_segment_bins = np.where(fragments == 0)[0]
    if centro_file is not None:
        # Read the file of the centromers
        with open(centro_file, "r", newline="") as centro:
            centro = csv.reader(centro, delimiter=" ")
            centro_pos = next(centro)
        # Sanity check: as many chroms as centromeres
        if len(chr_segment_bins) != len(centro_pos):
            sys.stderr.write("ERROR: Number of chromosomes and centromeres differ.")
            sys.exit(1)
        # Get bins of centromeres
        centro_bins = np.zeros(len(centro_pos))
        for i in range(len(chr_segment_bins)):
            if (i + 1) < len(chr_segment_bins):
                subfrags = fragments[chr_segment_bins[i] : chr_segment_bins[i + 1]]
            else:
                subfrags = fragments[chr_segment_bins[i] :]
            # index of last fragment starting before centro in same chrom
            centro_bins[i] = chr_segment_bins[i] + max(
                np.where((subfrags["start_pos"][:] // int(centro_pos[i])) == 0)[0]
            )
        # Combine centro and chrom bins into a single array. Values are start
        # bins of arms
        chr_segment_bins = np.sort(np.concatenate((chr_segment_bins, centro_bins)))
    return list(chr_segment_bins)


def get_chr_segment_length(fragments, chr_segment_bins):
    """Compute a list of the length of the different objects (arm or 
    chromosome) given by chr_segment_bins.
    
    Parameters
    ----------
    fragments : pandas.DataFrame
        Table containing in the first coulum the ID of the fragment, in the 
        second the names of the chromosome in the third and fourth the start 
        position and the end position of the fragment. The file have no header.
        (File like the 'fragments_list.txt' from hicstuff)
    chr_segment_bins : list of floats
        The start position of chromosomes/arms to compute the distance law on 
        each chromosome/arm separately.
        
    Returns
    -------
    list of numpy.ndarray:
        The length in base pairs of each chromosome or arm.
    """
    chr_segment_length = [None] * len(chr_segment_bins)
    # Iterate in chr_segment_bins in order to obtain the size of each chromosome/arm
    for i in range(len(chr_segment_bins) - 1):
        # Obtain the size of the chromosome/arm, the if loop is to avoid the
        # case of arms where the end position of the last fragments doesn't
        # mean th size of arm. If it's the right we have to remove the size of
        # the left arm.
        if (
            fragments["start_pos"].iloc[int(chr_segment_bins[i])] == 0
            or fragments["start_pos"][int(chr_segment_bins[i])] == 1
        ):
            n = fragments["end_pos"].iloc[int(chr_segment_bins[i + 1]) - 1]
        else:
            n = (
                fragments["end_pos"].iloc[int(chr_segment_bins[i + 1]) - 1]
                - fragments["end_pos"].iloc[int(chr_segment_bins[i]) - 1]
            )
        chr_segment_length[i] = n
    # Case of the last xs where we take the last end position
    if (
        fragments["start_pos"][int(chr_segment_bins[-2])] == 0
        or fragments["start_pos"][int(chr_segment_bins[-2])] == 1
    ):
        n = fragments["end_pos"].iloc[-1]
    else:
        n = (
            fragments["end_pos"].iloc[-1]
            - fragments["end_pos"].iloc[int(chr_segment_bins[-2]) - 1]
        )
    chr_segment_length[-1] = n
    return chr_segment_length


def logbins_xs(
    fragments, chr_segment_bins, chr_segment_length, base=1.1, circular=False
):
    """Compute the logbins of each chromosome/arm in order to have theme to
    compute distance law. At the end you will have bins of increasing with a 
    logspace with the base of the value given in base.
    
    Parameters
    ----------
    fragments : pandas.DataFrame
        Table containing in the first coulum the ID of the fragment, in the 
        second the names of the chromosome in the third and fourth the start 
        position and the end position of the fragment. The file have no header.
        (File like the 'fragments_list.txt' from hicstuff)
    chr_segment_bins : list of floats
        The start position of chromosomes/arms to compute the distance law on 
        each chromosome/arm separately.
    chr_segment_length: list of floats
        List of the size in base pairs of the different arms or chromosomes.
    base : float
        Base use to construct the logspace of the bins, 1.1 by default.
    circular : bool
        If True, calculate the distance as the chromosome is circular. Default 
        value is False.
        
    Returns
    -------
    list of numpy.ndarray :
        The start coordinate of each bin one array per chromosome or arm.
    """
    # Create the xs array and a list of the length of the chromosomes/arms
    xs = [None] * len(chr_segment_bins)
    # Iterate in chr_segment_bins in order to make the logspace
    for i in range(len(chr_segment_length)):
        n = chr_segment_length[i]
        # if the chromosome is circular the mawimum distance between two reads
        # are divided by two
        if circular:
            n /= 2
        n_bins = int(np.log(n) / np.log(base) + 1)
        # For each chromosome/arm compute a logspace to have the logbin
        # equivalent to the size of the arms and increasing size of bins
        xs[i] = np.unique(
            np.logspace(0, n_bins - 1, num=n_bins, base=base, dtype=np.int)
        )
    return xs


def circular_distance_law(distance, chr_segment_length, chr_bin):
    """Recalculate the distance to return the distance in a circular chromosome
    and not the distance between the two genomic positions.

    Parameters
    ----------
    chr_segment_bins : list of floats
        The start position of chromosomes/arms to compute the distance law on 
        each chromosome/arm separately.
    chr_segment_length: list of floats
        List of the size in base pairs of the different arms or chromosomes.
    distance : int
        Distance between two fragments with a contact.

    Returns
    -------
    int :
        The real distance in the chromosome circular and not the distance 
        between two genomic positions

    Examples
    --------
    >>> circular_distance_law(7500, [2800, 9000], 1)
    1500
    >>> circular_distance_law(1300, [2800, 9000], 0)
    1300
    >>> circular_distance_law(1400, [2800, 9000], 0)
    1400
    """
    chr_len = chr_segment_length[chr_bin]
    if distance > chr_len / 2:
        distance = chr_len - distance
    return distance


def get_pairs_distance(
    line, fragments, chr_segment_bins, chr_segment_length, xs, ps, circular=False
):
    """From a line of a pair reads file, filter -/+ or +/- reads, keep only the 
    reads in the same chromosome/arm and compute the distance of the the two
    fragments. It modify the input ps in order to count or not the line given. 
    It will add one in the logbin corresponding to the distance.

    Parameters
    ----------
    line : OrderedDict 
        Line of a pair reads file with the these keys readID, chr1, pos1, chr2,
        pos2, strand1, strand2, frag1, frag2. The values are in a dictionnary.
    fragments : pandas.DataFrame
        Table containing in the first coulum the ID of the fragment, in the 
        second the names of the chromosome in the third and fourth the start 
        position and the end position of the fragment. The file have no header.
        (File like the 'fragments_list.txt' from hicstuff)
    chr_segment_bins : list of floats
        The start position of chromosomes/arms to compute the distance law on 
        each chromosome/arm separately.
    chr_segment_length: list of floats
        List of the size in base pairs of the different arms or chromosomes.
    xs : list of lists
        The start coordinate of each bin one array per chromosome or arm.
    ps : list of lists
        The sum of contact already count. xs and ps should have the same 
        dimensions.
    circular : bool
        If True, calculate the distance as the chromosome is circular. Default 
        value is False.
    """
    # We only keep the event +/+ or -/-. This is done to avoid to have any
    # event of uncut which are not possible in these events. We can remove the
    # good events of +/- or -/+ because we don't need a lot of reads to compute
    # the distance law and if we eliminate these reads we do not create others
    # biases as they should have the same distribution.
    if line["strand1"] == line["strand2"]:
        # Find in which chromosome/arm are the fragment 1 and 2.
        chr_bin1 = (
            np.searchsorted(chr_segment_bins, int(line["frag1"]), side="right") - 1
        )
        chr_bin2 = (
            np.searchsorted(chr_segment_bins, int(line["frag2"]), side="right") - 1
        )
        # We only keep the reads with the two fragments in the same chromosome
        # or arm.
        if chr_bin1 == chr_bin2:
            # For the reads -/-, the fragments should be religated with both
            # their start position (position in the left on the genomic
            # sequence, 5'). For the reads +/+ it's the contrary. We compute
            # the distance as the distance between the two extremities which
            # are religated.
            if line["strand1"] == "-":
                distance = abs(
                    np.array(fragments["start_pos"][int(line["frag1"])])
                    - np.array(fragments["start_pos"][int(line["frag2"])])
                )
            if line["strand1"] == "+":
                distance = abs(
                    np.array(fragments["end_pos"][int(line["frag1"])])
                    - np.array(fragments["end_pos"][int(line["frag2"])])
                )
            if circular:
                distance = circular_distance_law(distance, chr_segment_length, chr_bin1)
            xs_temp = xs[chr_bin1][:]
            # Find the logbins in which the distance is and add one to the sum
            # of contact.
            ps_indice = np.searchsorted(xs_temp, distance, side="right") - 1
            ps[chr_bin1][ps_indice] += 1


def get_names(fragments, chr_segment_bins):
    """Make a list of the names of the arms or the chromosomes.

    Parameters
    ----------
    fragments : pandas.DataFrame
        Table containing in the first coulum the ID of the fragment, in the 
        second the names of the chromosome in the third and fourth the start 
        position and the end position of the fragment. The file have no header.
        (File like the 'fragments_list.txt' from hicstuff)
    chr_segment_bins : list of floats
        The start position of chromosomes/arms to compute the distance law on 
        each chromosome/arm separately.

    Returns
    -------
    list of floats : 
        List of the labels given to the curves. It will be the name of the arms
        or chromosomes.
    """
    # Get the name of the chromosomes.
    chr_names = np.unique(fragments["chrom"])
    # Case where they are separate in chromosomes
    if len(chr_segment_bins) == len(chr_names):
        names = list(chr_names)
    # Case where they are separate in arms
    else:
        names = []
        for chr in chr_names:
            names.append(chr + "_left")
            names.append(chr + "_rigth")
    return names


def get_distance_law(
    pairs_reads_file,
    fragments_file,
    centro_file=None,
    base=1.1,
    outdir=None,
    circular=False,
):
    """Compute distance law as a function of the genomic coordinate aka P(s).
    Bin length increases exponentially with distance. Works on pairs file 
    format from 4D Nucleome Omics Data Standards Working Group. If the genome 
    is composed of several chromosomes and you want to compute the arms 
    separately, provide a file with the positions of centromers. Create a file 
    with three coulumns separated by a tabulation. The first column contains 
    the xs, the second the ps and the third the name of the arm or chromosome. 
    The file is create in the directory given in outdir or in the current 
    directory if no directory given.

    Parameters
    ----------
    pairs_reads_file : string
        Path of a pairs file format from 4D Nucleome Omics Data Standards 
        Working Group with the 8th and 9th coulumns are the ID of the fragments
        of the reads 1 and 2.
    fragments_file : path
        Path of a table containing in the first column the ID of the fragment,
        in the second the names of the chromosome in the third and fourth 
        the start position and the end position of the fragment. The file have 
        no header. (File like the 'fragments_list.txt' from hicstuff)
    centro_file : None or str
        None or path to a file with the genomic positions of the centromers 
        sorted as the chromosomes separated by a space. The file have only one 
        line.
    base : float
        Base use to construct the logspace of the bins - 1.1 by default.
    outdir : None or str
        Directory of the output file. If no directory given, will be replace by
        the current directory.
    circular : bool
        If True, calculate the distance as the chromosome is circular. Default 
        value is False. Cannot be True if centro_file is not None     
    """
    # Sanity check : centro_fileition should be None if chromosomes are
    # circulars (no centromeres is circular chromosomes).
    if circular and centro_file != None:
        print("Chromosomes cannot have a centromere and be circular")
        raise ValueError
    # Import third columns of fragments file
    fragments = pd.read_csv(fragments_file, sep="\t", header=0, usecols=[0, 1, 2, 3])
    # Calculate the indice of the bins to separate into chromosomes/arms
    chr_segment_bins = get_chr_segment_bins_index(fragments, centro_file)
    # Calculate the length of each chromosoms/arms
    chr_segment_length = get_chr_segment_length(fragments, chr_segment_bins)
    xs = logbins_xs(fragments, chr_segment_bins, chr_segment_length, base, circular)
    # Create the list of p(s) with one array for each chromosome/arm and each
    # array contain as many values as in the logbin
    ps = [None] * len(chr_segment_bins)
    for i in range(len(xs)):
        ps[i] = [0] * len(xs[i])
    # Read the pair reads file
    with open(pairs_reads_file, "r", newline="") as reads:
        # Remove the line of the header
        header_length = len(hio.get_pairs_header(pairs_reads_file))
        for i in range(header_length):
            next(reads)
        # Reads all the others lines and put the values in a dictionnary with
        # the keys : 'readID', 'chr1', 'pos1', 'chr2', 'pos2', 'strand1',
        # 'strand2', 'frag1', 'frag2'
        reader = csv.DictReader(
            reads,
            fieldnames=[
                "readID",
                "chr1",
                "pos1",
                "chr2",
                "pos2",
                "strand1",
                "strand2",
                "frag1",
                "frag2",
            ],
            delimiter=" ",
        )
        for line in reader:
            # Iterate in each line of the file after the header
            get_pairs_distance(
                line, fragments, chr_segment_bins, chr_segment_length, xs, ps, circular
            )
    # Divide the number of contacts by the area of the logbin
    for i in range(len(xs)):
        n = chr_segment_length[i]
        for j in range(len(xs[i]) - 1):
            # Use the area of a trapezium to know the area of the logbin with n
            # the size of the matrix.
            ps[i][j] /= ((2 * n - xs[i][j + 1] - xs[i][j]) / 2) * (
                (1 / np.sqrt(2)) * (xs[i][j + 1] - xs[i][j])
            )
        # Case of the last logbin which is an isosceles rectangle triangle
        ps[i][-1] /= ((n - xs[i][-1]) ** 2) / 2
    names = get_names(fragments, chr_segment_bins)
    export_distance_law(xs, ps, names, outdir)


def normalize_distance_law(xs, ps):
    """Normalize the distance in order to have the sum of the ps values between
    1000 (1kb) until the end of the array equal to one and limit the effect of 
    coverage between two conditions/chromosomes/arms when you compare them 
    together. If we have a list of ps, it will normalize until the length of 
    the shorter object.

    Parameters
    ----------
    xs : list of numpy.ndarray
        list of logbins corresponding to the ps.
    ps : list of numpy.ndarray
        Average ps or list of ps of the chromosomes/arms. xs and ps have to 
        have the same shape.

    Returns
    -------
    list of numpy.ndarray :
        List of ps each normalized separately.
    """
    # Sanity check: xs and ps have the same dimension
    if np.shape(xs) != np.shape(ps):
        print(np.shape(xs), np.shape(ps))
        sys.stderr.write("ERROR: xs and ps should have the same dimension.")
        sys.exit(1)
    # Take the mean of xs as superior limit to choose the limits of the
    # interval use for the normalisation
    min_xs = len(min(xs, key=len))
    normed_ps = [None] * len(ps)
    for j, my_list in enumerate(ps):
        # Iterate on the different ps to normalize each of theme separately
        sum_values = 0
        for i, value in enumerate(my_list):
            # Keep only the value between 1kb and the length of the shorter
            # object given in the list
            if (xs[j][i] > 1000) and (i < min_xs):
                sum_values += value
        if sum_values == 0:
            sum_values += 1
            warnings.warn(
                "No values of p(s) in the interval 1000 and "
                + str(xs[j][min_xs])
                + " base pairs, this list hasn't been normalized"
            )
        # Make the normalisation
        normed_ps[j] = ps[j] / sum_values
    return normed_ps


def average_distance_law(xs, ps):
    """Compute the average distance law between the file the different distance
    law of the chromosomes/arms.

    Parameters
    ----------
    xs : list of numpy.ndarray
        The list of logbins.
    ps : list of lists of floats
        The list of numpy.ndarray.

    Returns
    -------
    numpy.ndarray :
        List of the xs with the max length.
    numpy.ndarray :
        List of the average_ps.
    """
    # Find longest chromosome / arm and make two arrays of this length for the
    # average distance law
    xs = max(xs, key=len)
    max_length = len(xs)
    ps_values = np.zeros(max_length)
    ps_occur = np.zeros(max_length)
    for chrom_ps in ps:
        # Iterate on ps in order to calculate the number of occurences (all the
        # chromossomes/arms are not as long as the longest one) and the sum of
        # the values of distance law.
        ps_occur[: len(chrom_ps)] += 1
        ps_values[: len(chrom_ps)] += chrom_ps
    # Make the mean
    averaged_ps = ps_values / ps_occur
    return xs, averaged_ps


def slope_distance_law(xs, ps):
    """Compute the slope of the loglog curve of the ps as the 
    [log(ps(n+1)) - log(ps(n))] / [log(n+1) - log(n)].
    Compute only list of ps, not list of array.

    Parameters
    ----------
    xs : list of numpy.ndarray
        The list of logbins.
    ps : list of numpy.ndarray
        The list of ps.

    Returns
    -------
    list of numpy.ndarray :
        The slope of the distance law. It will be shorter of one value than the
        ps given initially.
    """
    slope = [None] * len(ps)
    for i in range(len(ps)):
        ps[i][ps[i] == 0] = 10 ** (-9)
        # Compute the slope
        slope_temp = np.log(np.array(ps[i][1:]) / np.array(ps[i][:-1])) / np.log(
            np.array(xs[i][1:]) / np.array(xs[i][:-1])
        )
        # The 2 is the intensity of the normalisation, it could be adapted.
        slope_temp[slope_temp == np.nan] = 10 ** (-15)
        slope[i] = ndimage.filters.gaussian_filter1d(slope_temp, 2)
    return slope


def plot_ps_slope(xs, ps, slope, labels, out_dir=None, inf=3000, sup=None):
    """Compute two plots, one with the different distance law of each 
    arm/chromosome and one with the slope of these curves. Generate a 
    svg file with savefig.

    Parameters
    ----------
    xs : list of numpy.ndarray
        The list of the logbins of each ps.
    ps : list of numpy.ndarray
        The list of ps.
    slope : list of numpy.ndarray
        The list of slope of the ps loglog curves, each list have one value 
        less than the xs and ps list.
    labels_file : List of string
        File of one column without header containing the names of the 
        different curves in the order in which they are given.
    out_dir : str
        Directory to create the file. By default it's None, and do not 
        create the file.
    inf : int 
        Value of the mimimum x of the window of the plot. Have to be strictly
        positive. By default 3000.
    sup : int 
        Value of the maximum x of the window of the plot. By default None.


    Returns
    matplotlib.plot :
        Plot of the ps with two windows : one with the distance law curves of 
        each arms/chromosomes in loglog scale and the slope (derivative) of 
        these curves in the second windows.
    """
    # Give the max value for sup if no value have been attributed
    if sup == "None":
        sup = max(max(xs, key=len))
    # Make the plot of distance law
    # Give a range of color
    cols = iter(cm.rainbow(np.linspace(0, 1, len(ps))))
    fig, (ax1, ax2) = plt.subplots(1, 2, sharex=True, figsize=(18, 10))
    plt.subplots_adjust(left=0.05, right=0.85, top=0.93, bottom=0.07)
    ax1.set_xlabel("Distance (pb)", fontsize="x-large")
    ax1.set_ylabel("P(s)", fontsize="x-large")
    ax1.set_title("Distance law", fontsize="xx-large")
    for i in range(len(ps)):
        # Iterate on the different distance law array and take them by order of
        # size in order to have the color scale equivalent to the size scale
        col = next(cols)
        ax1.loglog(xs[i], ps[i], label=labels[i], color=col, linewidth=0.8)
    # Make the same plot with the slope
    cols = iter(cm.rainbow(np.linspace(0, 1, len(slope))))
    ax2.set_xlabel("Distance (pb)", fontsize="x-large")
    ax2.set_ylabel("Slope", fontsize="x-large")
    ax2.set_title("Slope of the distance law", fontsize="xx-large")
    ax2.set_xlim([inf, sup])
    xs2 = [None] * len(xs)
    for i in range(len(slope)):
        xs2[i] = xs[i][:-1]
        col = next(cols)
        ax2.semilogx(
            xs2[i],
            slope[i],
            label=labels[i],
            color=col,
            linewidth=0.8,
            subsx=[2, 3, 4, 5, 6, 7, 8, 9],
        )
    ax2.legend(loc="upper left", bbox_to_anchor=(1.02, 1.00), ncol=1, fontsize="large")
    # Save the figure in svg
    if out_dir is not None:
        plt.savefig(out_dir)
    return fig, ax1, ax2
