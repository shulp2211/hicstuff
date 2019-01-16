#!/usr/bin/env python3
# coding: utf-8

"""
Functions used to write GRAAL compatible sparse matrices.
"""

from Bio import SeqIO, SeqUtils
from Bio.Restriction import RestrictionBatch
import os, sys
import collections
import copy
import matplotlib.pyplot as plt
import pandas as pd

DEFAULT_FRAGMENTS_LIST_FILE_NAME = "fragments_list.txt"
DEFAULT_INFO_CONTIGS_FILE_NAME = "info_contigs.txt"
DEFAULT_SPARSE_MATRIX_FILE_NAME = "abs_fragments_contacts_weighted.txt"
DEFAULT_KB_BINNING = 1
DEFAULT_THRESHOLD_SIZE = 0
# Most used enzyme for eukaryotes
DEFAULT_ENZYME = "DpnII"
# If using evenly-sized chunks instead of restriction
# enzymes, they shouldn't be too short
DEFAULT_MIN_CHUNK_SIZE = 50


def write_frag_info(
    fasta,
    enzyme,
    size=DEFAULT_THRESHOLD_SIZE,
    circular=False,
    output_contigs=DEFAULT_INFO_CONTIGS_FILE_NAME,
    output_frags=DEFAULT_FRAGMENTS_LIST_FILE_NAME,
    output_dir=None,
):
    """Digest and write fragment information

    Write the fragments_list.txt and info_contigs.txt that are necessary for
    instaGRAAL to run.

    Parameters
    ----------
    fasta : pathlib.Path or str
        The path to the reference genome
    enzyme : str or int
        If a string, must be the name of an enzyme (e.g. DpnII) and the genome
        will be cut at the enzyme's restriction sites. If a number, the genome
        will be cut uniformly into chunks with length equal to that number.
    size : float, optional
        Size below which shorter contigs are discarded. Default is 0, i.e. all
        contigs are retained.
    circular : bool, optional
        Whether the genome is circular. Default is False.
    output_contigs : str, optional
        The name of the file with contig info. Default is info_contigs.txt
    output_frags : str, optional
        The name of the file with fragment info. Default is fragments_list.txt
    output_dir : [type], optional
        The path to the output directory, which will be created if not already
        existing. Default is the current directory.
    """

    try:
        my_enzyme = RestrictionBatch([enzyme]).get(enzyme)
    except ValueError:
        my_enzyme = max(int(enzyme), DEFAULT_MIN_CHUNK_SIZE)

    records = SeqIO.parse(fasta, "fasta")

    try:
        info_contigs_path = os.path.join(output_dir, output_contigs)
        frag_list_path = os.path.join(output_dir, output_frags)
    except AttributeError:
        info_contigs_path = output_contigs
        frag_list_path = output_frags

    with open(info_contigs_path, "w") as info_contigs:

        info_contigs.write("contig\tlength\tn_frags\tcumul_length\n")

        with open(frag_list_path, "w") as fragments_list:

            fragments_list.write(
                "id\tchrom\tstart_pos" "\tend_pos\tsize\tgc_content\n"
            )

            total_frags = 0

            for record in records:
                my_seq = record.seq
                contig_name = record.id
                contig_length = len(my_seq)
                if contig_length < int(size):
                    continue
                try:
                    my_frags = my_enzyme.catalyze(my_seq, linear=not circular)
                except AttributeError:
                    n = len(my_seq)
                    my_frags = (
                        my_seq[i : min(i + my_enzyme, n)]
                        for i in range(0, len(my_seq), my_enzyme)
                    )
                n_frags = 0

                current_id = 1
                start_pos = 0
                for frag in my_frags:
                    size = len(frag)
                    if size > 0:
                        end_pos = start_pos + size
                        gc_content = SeqUtils.GC(frag) / 100.0

                        current_fragment_line = "%s\t%s\t%s\t%s\t%s\t%s\n" % (
                            current_id,
                            contig_name,
                            start_pos,
                            end_pos,
                            size,
                            gc_content,
                        )

                        fragments_list.write(current_fragment_line)

                        try:
                            assert (current_id == 1 and start_pos == 0) or (
                                current_id > 1 and start_pos > 0
                            )
                        except AssertionError:
                            print((current_id, start_pos), file=sys.stderr)
                            raise
                        start_pos = end_pos
                        current_id += 1
                        n_frags += 1

                current_contig_line = "%s\t%s\t%s\t%s\n" % (
                    contig_name,
                    contig_length,
                    n_frags,
                    total_frags,
                )
                total_frags += n_frags
                info_contigs.write(current_contig_line)


def write_sparse_matrix(
    intersect_sorted,
    fragments_list=DEFAULT_SPARSE_MATRIX_FILE_NAME,
    output_file=DEFAULT_SPARSE_MATRIX_FILE_NAME,
    output_dir=None,
    bedgraph=False,
):
    """Generate a GRAAL-compatible sparse matrix from a sorted intersection
    BED file.
    """

    try:
        output_file_path = os.path.join(output_dir, output_file)
    except AttributeError:
        output_file_path = output_file

    print("Building fragment position dictionary...")
    # Build dictionary of absolute positions and fragment ids
    ids_and_positions = dict()
    with open(fragments_list) as fraglist_handle:
        _ = next(fraglist_handle)
        my_id = 0
        for line in fraglist_handle:
            contig_name, position, end = line.rstrip("\n").split("\t")[1:4]
            ids_and_positions[(contig_name, position, end)] = my_id
            my_id += 1
    print("Done.")

    print("Counting contacts...")

    # Detect and count contacts between fragments
    contacts = collections.Counter()
    with open(intersect_sorted) as intersect_handle:
        is_forward = True
        for line in intersect_handle:
            if is_forward:
                read_forward = line.rstrip("\n").split("\t")
                is_forward = False
                continue
            else:
                (
                    _,
                    start_forward,
                    end_forward,
                    name_forward,
                    orientation_forward,
                    contig_forward,
                    start_fragment_forward,
                    end_fragment_forward,
                ) = read_forward

                read_reverse = line.rstrip("\n").split("\t")
                (
                    _,
                    start_reverse,
                    end_reverse,
                    name_reverse,
                    orientation_reverse,
                    contig_reverse,
                    start_fragment_reverse,
                    end_fragment_reverse,
                ) = read_reverse

                # Detect contacts in the form of matching readnames
                # (last two characters are stripped in case read
                # name ends with '/1' or '/2')
                short_name_forward = name_forward.split()[0]
                short_name_reverse = name_reverse.split()[0]
                if short_name_forward == short_name_reverse:
                    abs_position_for = (
                        contig_forward,
                        start_fragment_forward,
                        end_fragment_forward,
                    )
                    abs_position_rev = (
                        contig_reverse,
                        start_fragment_reverse,
                        end_fragment_reverse,
                    )
                    try:
                        id_frag_for = ids_and_positions[abs_position_for]
                        id_frag_rev = ids_and_positions[abs_position_rev]
                    except KeyError:
                        print(
                            (
                                "Couldn't find matching fragment "
                                "id for position {} or position "
                                "{}".format(abs_position_for, abs_position_rev)
                            )
                        )
                    else:
                        fragment_pair = tuple(
                            sorted((id_frag_for, id_frag_rev))
                        )
                        contacts[fragment_pair] += 1
                        # print("Successfully added contact between"
                        #       " {} and {}".format(id_fragment_forward,
                        #                           id_fragment_reverse))
                    finally:
                        is_forward = True
                else:
                    # If for some reason some reads are not properly
                    # interleaved, just skip the previous line and
                    # move on with the current line
                    # print("Read name {} does not match successor {}, "
                    # "reads are not properly interleaved".format(name_forward,
                    #                                             name_reverse))
                    read_forward = copy.deepcopy(read_reverse)
                    is_forward = False
    print("Done.")

    print("Writing sparse matrix...")
    if bedgraph:
        # Get reverse mapping between fragments ids and pos
        positions_and_ids = {
            id: pos for pos, id in list(ids_and_positions.items())
        }

        def parse_coord(coord):
            return "\t".join(str(x) for x in coord)

        with open(output_file_path, "w") as output_handle:
            for id_pair in sorted(contacts):
                id_fragment_a, id_fragment_b = id_pair
                nb_contacts = contacts[id_pair]
                coord_a = parse_coord(positions_and_ids[id_fragment_a])
                coord_b = parse_coord(positions_and_ids[id_fragment_b])
                line_to_write = "{}\t{}\t{}\n".format(
                    coord_a, coord_b, nb_contacts
                )
                output_handle.write(line_to_write)

    else:
        with open(output_file_path, "w") as output_handle:
            output_handle.write("id_frag_a\tid_frag_b\tn_contact\n")
            for id_pair in sorted(contacts):
                id_fragment_a, id_fragment_b = id_pair
                nb_contacts = contacts[id_pair]
                line_to_write = "{}\t{}\t{}\n".format(
                    id_fragment_a, id_fragment_b, nb_contacts
                )
                output_handle.write(line_to_write)

    print("Done.")


def dade_to_GRAAL(
    filename,
    output_matrix=DEFAULT_SPARSE_MATRIX_FILE_NAME,
    output_contigs=DEFAULT_INFO_CONTIGS_FILE_NAME,
    output_frags=DEFAULT_SPARSE_MATRIX_FILE_NAME,
    output_dir=None,
):
    """Convert a matrix from DADE format (https://github.com/scovit/dade)
    to a GRAAL-compatible format. Since DADE matrices contain both fragment
    and contact information all files are generated at the same time.
    """
    import numpy as np

    with open(output_matrix, "w") as sparse_file:
        sparse_file.write("id_frag_a\tid_frag_b\tn_contact")
        with open(filename) as file_handle:
            first_line = file_handle.readline()
            for row_index, line in enumerate(file_handle):
                dense_row = np.array(line.split("\t")[1:], dtype=np.int32)
                for col_index in np.nonzero(dense_row)[0]:
                    line_to_write = "{}\t{}\t{}\n".format(
                        row_index, col_index, dense_row[col_index]
                    )
                    sparse_file.write(line_to_write)

        print("Matrix file written")

    header = first_line.split("\t")
    bin_type = header[0]
    if bin_type == '"RST"':
        print("I detected fragment-wise binning")
    elif bin_type == '"BIN"':
        print("I detected fixed size binning")
    else:
        print(
            (
                "Sorry, I don't understand this matrix's "
                "binning: I read {}".format(str(bin_type))
            )
        )

    header_data = [
        header_elt.replace("'", "")
        .replace('"', "")
        .replace("\n", "")
        .split("~")
        for header_elt in header[1:]
    ]

    (
        global_frag_ids,
        contig_names,
        local_frag_ids,
        frag_starts,
        frag_ends,
    ) = np.array(list(zip(*header_data)))

    frag_starts = frag_starts.astype(np.int32) - 1
    frag_ends = frag_ends.astype(np.int32) - 1
    frag_lengths = frag_ends - frag_starts

    total_length = len(global_frag_ids)

    with open(output_contigs, "w") as info_contigs:

        info_contigs.write("contig\tlength\tn_frags\tcumul_length\n")

        cumul_length = 0

        for contig in collections.OrderedDict.fromkeys(contig_names):

            length_tig = np.sum(frag_lengths[contig_names == contig])
            n_frags = collections.Counter(contig_names)[contig]
            line_to_write = "%s\t%s\t%s\t%s\n" % (
                contig,
                length_tig,
                n_frags,
                cumul_length,
            )
            info_contigs.write(line_to_write)
            cumul_length += n_frags

        print("Contig list written")

    with open(output_frags, "w") as fragments_list:

        fragments_list.write(
            "id\tchrom\tstart_pos\tend_pos" "\tsize\tgc_content\n"
        )
        bogus_gc = 0.5

        for i in range(total_length):
            line_to_write = "%s\t%s\t%s\t%s\t%s\t%s\n" % (
                int(local_frag_ids[i]) + 1,
                contig_names[i],
                frag_starts[i],
                frag_ends[i],
                frag_lengths[i],
                bogus_gc,
            )
            fragments_list.write(line_to_write)

        print("Fragment list written")


def frag_len(
    output_frags=DEFAULT_FRAGMENTS_LIST_FILE_NAME,
    output_dir=None,
    plot=False,
    fig_path=None,
):
    """
    Generates summary of fragment length distribution based on an
    input fragment file. Can optionally show a histogram instead
    of text summary.
    Parameters
    ----------
    output_frags : str
        Path to the output list of fragments.
    output_dir : str
        Directory where the list should be saved.
    plot : bool
        Wether a histogram of fragment length should be shown.
    fig_path : str
        If a path is given, the figure will be saved instead of shown.
    """

    try:
        frag_list_path = os.path.join(output_dir, output_frags)
    except AttributeError:
        frag_list_path = output_frags
    frags = pd.read_csv(frag_list_path, sep="\t")
    nfrags = frags.shape[0]
    med_len = frags["size"].median()
    nbins = 40
    if plot:
        fig, ax = plt.subplots()
        n, bins, patches = ax.hist(frags["size"], bins=nbins)

        ax.set_xlabel("Fragment length [bp]")
        ax.set_ylabel("Number of fragments")
        ax.set_title("Distribution of restriction fragment length")
        ax.annotate(
            "Total fragments: {}".format(nfrags),
            xy=(0.95, 0.95),
            xycoords="axes fraction",
            fontsize=12,
            horizontalalignment="right",
            verticalalignment="top",
        )
        ax.annotate(
            "Median length: {}".format(med_len),
            xy=(0.95, 0.90),
            xycoords="axes fraction",
            fontsize=12,
            horizontalalignment="right",
            verticalalignment="top",
        )
        # Tweak spacing to prevent clipping of ylabel
        fig.tight_layout()
        if fig_path:
            plt.savefig(fig_path)
        else:
            plt.show()
    else:
        print(
            "Genome digested into {0} fragments with a median "
            "length of {1}".format(nfrags, med_len),
            file=sys.stderr,
        )
