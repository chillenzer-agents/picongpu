/* SPDX-FileCopyrightText: 2013-2024 Rene Widera
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <boost/program_options.hpp>
#include <boost/program_options/cmdline.hpp>
#include <boost/program_options/options_description.hpp>
#include <boost/program_options/variables_map.hpp>

#include <cstdlib>
#include <iostream> // std::cerr

#include <mpi.h>


#define MPI_CHECK(cmd)                                                                                                \
    {                                                                                                                 \
        int error = cmd;                                                                                              \
        if(error != MPI_SUCCESS)                                                                                      \
        {                                                                                                             \
            printf("<%s>:%i ", __FILE__, __LINE__);                                                                   \
            throw std::runtime_error(std::string("[MPI] Error"));                                                     \
        }                                                                                                             \
    }

namespace po = boost::program_options;

/*! gets hostRank
 *
 * Computes the node-local rank (the index of this process among all processes
 * sharing the same node) via MPI_Comm_split_type.
 */
int getHostRank()
{
    int hostRank;
    int myrank;

    MPI_CHECK(MPI_Comm_rank(MPI_COMM_WORLD, &myrank));

    MPI_Comm nodeComm;
    MPI_CHECK(MPI_Comm_split_type(MPI_COMM_WORLD, MPI_COMM_TYPE_SHARED, myrank, MPI_INFO_NULL, &nodeComm));
    MPI_CHECK(MPI_Comm_rank(nodeComm, &hostRank));
    MPI_CHECK(MPI_Comm_free(&nodeComm));

    return hostRank;
}

int getMyRank()
{
    int myrank;
    MPI_CHECK(MPI_Comm_rank(MPI_COMM_WORLD, &myrank));
    return myrank;
}

int getTotalRanks()
{
    int totalnodes;
    MPI_CHECK(MPI_Comm_size(MPI_COMM_WORLD, &totalnodes));
    return totalnodes;
}

int main(int argc, char** argv)
{
    bool localRank = false;
    bool myRank = false;
    bool totalRank = false;

    po::options_description desc("Allowed options");
    desc.add_options()(
        "help,h",
        "produce help message")("mpi_host_rank", po::value<bool>(&localRank)->zero_tokens(), "get local mpi rank")(
        "mpi_rank",
        po::value<bool>(&myRank)->zero_tokens(),
        "get mpi rank")("mpi_size", po::value<bool>(&totalRank)->zero_tokens(), "get count of mpi ranks");

    // parse command line options and config file and store values in vm
    po::variables_map vm;
    po::store(boost::program_options::parse_command_line(argc, argv, desc), vm);
    po::notify(vm);

    // print help message and quit simulation
    if(vm.count("help"))
    {
        std::cerr << desc << "\n";
        return 0;
    }

    MPI_CHECK(MPI_Init(&argc, &argv));
    if(localRank)
        std::cout << "mpi_host_rank: " << getHostRank() << std::endl;
    if(myRank)
        std::cout << "mpi_rank: " << getMyRank() << std::endl;
    if(totalRank)
        std::cout << "mpi_size: " << getTotalRanks() << std::endl;


    MPI_CHECK(MPI_Finalize());

    return 0;
}
