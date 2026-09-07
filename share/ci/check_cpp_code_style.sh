#!/bin/bash

set -e
set -o pipefail


#############################################################################
# Conformance with Alpaka: Do not write __global__ CUDA kernels directly    #
# Enforce angle brackets <...> for includes of external library files       #
# Disallow doxygen with \                                                   #
#                                                                           #
# When called without arguments the whole include/ and share/ trees are     #
# checked (directory mode). When called by pre-commit with a list of        #
# changed files each file is mapped to the checks applying to its location  #
# and every check is a single batched grep over that scope.                 #
#############################################################################

if [ "$#" -eq 0 ] ; then
    ###########################################################################
    # Conformance with Alpaka: Do not write __global__ CUDA kernels directly  #
    ###########################################################################
    test/hasCudaGlobalKeyword include/pmacc
    test/hasCudaGlobalKeyword share/pmacc/examples
    test/hasCudaGlobalKeyword include/picongpu
    test/hasCudaGlobalKeyword share/picongpu/examples

    ###########################################################################
    # Enforce angle brackets <...> for includes of external library files     #
    ###########################################################################
    test/hasExtLibIncludeBrackets include boost
    test/hasExtLibIncludeBrackets include alpaka
    test/hasExtLibIncludeBrackets include mallocMC
    test/hasExtLibIncludeBrackets include/picongpu pmacc
    test/hasExtLibIncludeBrackets share/picongpu/examples pmacc
    test/hasExtLibIncludeBrackets share/picongpu/examples boost
    test/hasExtLibIncludeBrackets share/picongpu/examples alpaka
    test/hasExtLibIncludeBrackets share/picongpu/examples mallocMC
    test/hasExtLibIncludeBrackets share/pmacc/examples pmacc

    ###########################################################################
    # Disallow doxygen with \                                                 #
    ###########################################################################
    test/hasWrongDoxygenStyle include param
    test/hasWrongDoxygenStyle include tparam
    test/hasWrongDoxygenStyle include see
    test/hasWrongDoxygenStyle include return
    test/hasWrongDoxygenStyle include treturn
    test/hasWrongDoxygenStyle share param
    test/hasWrongDoxygenStyle share tparam
    test/hasWrongDoxygenStyle share see
    test/hasWrongDoxygenStyle share return
    test/hasWrongDoxygenStyle share treturn

    exit 0
fi

#############################################################################
# Per-file mode (invoked by pre-commit with the list of changed files)      #
#                                                                           #
# Scope mapping (kept identical to the directory mode above):               #
#   __global__        : include/picongpu, include/pmacc,                    #
#                       share/picongpu/examples, share/pmacc/examples       #
#   pmacc brackets    : include/picongpu, share/picongpu/examples,          #
#                       share/pmacc/examples                                #
#   boost/alpaka/     : include (any), share/picongpu/examples              #
#   mallocMC brackets                                                       #
#   doxygen           : include (any), share (any)                          #
# pmacc self-includes ("./pmacc/...") inside include/pmacc stay allowed.    #
#############################################################################

globalKeywordsFiles=()
includeBracketFiles=()       # boost, alpaka, mallocMC
picongpuBracketFiles=()      # boost, alpaka, mallocMC, pmacc
sharePicongpuBracketFiles=() # boost, alpaka, mallocMC, pmacc
sharePmaccBracketFiles=()    # pmacc
includeDoxygenFiles=()
shareDoxygenFiles=()

for file in "$@" ; do
    file=${file#./}
    case "$file" in
        include/picongpu/*)
            globalKeywordsFiles+=("$file")
            picongpuBracketFiles+=("$file")
            includeDoxygenFiles+=("$file")
            ;;
        include/pmacc/*)
            globalKeywordsFiles+=("$file")
            includeBracketFiles+=("$file")
            includeDoxygenFiles+=("$file")
            ;;
        include/*)
            includeBracketFiles+=("$file")
            includeDoxygenFiles+=("$file")
            ;;
        share/picongpu/examples/*)
            globalKeywordsFiles+=("$file")
            sharePicongpuBracketFiles+=("$file")
            shareDoxygenFiles+=("$file")
            ;;
        share/pmacc/examples/*)
            globalKeywordsFiles+=("$file")
            sharePmaccBracketFiles+=("$file")
            shareDoxygenFiles+=("$file")
            ;;
        share/*)
            shareDoxygenFiles+=("$file")
            ;;
    esac
done

if [ "${#globalKeywordsFiles[@]}" -gt 0 ] ; then
    printf '%s\n' "${globalKeywordsFiles[@]}" | test/hasCudaGlobalKeyword -
fi

if [ "${#includeBracketFiles[@]}" -gt 0 ] ; then
    for lib in boost alpaka mallocMC ; do
        printf '%s\n' "${includeBracketFiles[@]}" | test/hasExtLibIncludeBrackets - "$lib"
    done
fi

if [ "${#picongpuBracketFiles[@]}" -gt 0 ] ; then
    for lib in boost alpaka mallocMC pmacc ; do
        printf '%s\n' "${picongpuBracketFiles[@]}" | test/hasExtLibIncludeBrackets - "$lib"
    done
fi

if [ "${#sharePicongpuBracketFiles[@]}" -gt 0 ] ; then
    for lib in pmacc boost alpaka mallocMC ; do
        printf '%s\n' "${sharePicongpuBracketFiles[@]}" | test/hasExtLibIncludeBrackets - "$lib"
    done
fi

if [ "${#sharePmaccBracketFiles[@]}" -gt 0 ] ; then
    printf '%s\n' "${sharePmaccBracketFiles[@]}" | test/hasExtLibIncludeBrackets - pmacc
fi

if [ "${#includeDoxygenFiles[@]}" -gt 0 ] ; then
    for keyword in param tparam see return treturn ; do
        printf '%s\n' "${includeDoxygenFiles[@]}" | test/hasWrongDoxygenStyle - "$keyword"
    done
fi

if [ "${#shareDoxygenFiles[@]}" -gt 0 ] ; then
    for keyword in param tparam see return treturn ; do
        printf '%s\n' "${shareDoxygenFiles[@]}" | test/hasWrongDoxygenStyle - "$keyword"
    done
fi

exit 0
