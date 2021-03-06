import sys
import os
from datetime import datetime
from immunogrep_global_variables import listofextension
from immunogrep_global_variables import descriptor_symbol
import immunogrep_immunogrepfile as readwrite
import traceback
import subprocess
# from bson.objectid import ObjectId


dna_codes = {
        'A':'T',
        'C':'G',
        'G':'C',
        'T':'A',
        'N':'N',
        'X':'X',
        '-':'-',
        'U':'A',
        'W':'W',
        'M':'K',
        'K':'M',
        'S':'S',
        'R':'Y',
        'Y':'R',

        'a':'t',
        'c':'g',
        'g':'c',
        't':'a',
        'u':'a',
        'w':'w',
        'n':'n',
        'm':'k',
        'k':'m',
        's':'s',
        'r':'y',
        'x':'x',
        'y':'r'
    }


def get_stdout(bash_command):
    """
        Temp space holder for get_stdout
    """
    time=str(datetime.now()).replace(' ','').replace(':','').replace('/','').replace('\\','').replace('-','')
    temp_file_name = 'scratch/stdout'+time+'.txt'
    os.system(bash_command +" > {0}".format(temp_file_name))
    with open(temp_file_name) as e:
        output = e.read().strip()
    os.system("rm '{0}'".format(temp_file_name))
    return output

def file_line_count(filepath):
    """

        Takes a file path as input. Returns

        .. warning::
            If path is not found, outputs: File does not exist
    """
    if os.path.isfile(filepath):
        return int(get_stdout("wc -l '{0}'".format(filepath)).split()[0])# int(subprocess.check_output(['wc', '-l', filepath]).split()[0]) => subprocess.check_output creates zombie processes, so want to avoid that?
    else:
        raise Exception('File does not exist: '+filepath)


def Reverse_Complement(x):
    """

        Takes in sequence x and returns its complement (?)
    """
    rc_list = [dna_codes[c] if c in dna_codes else 'N' if ord(c) <91 else 'n' for c in reversed(x)]
    return ''.join(rc_list)


#we will use this function for splitting a single file into multiple little files.
#this will be useufl for multithreading purposes
#filepath => input file
#num_files_to_make => number of split files to create
#number_lines_per_seq => number of lines that correspond to a single sequence (fastq files = 4, fastqfiles = 2)
#contains_header_row => IMPORTANT, WE CANNOT JUST USE THE SPLIT COMMAND, INSTEAD WE HAVE TO USE AWK COMMAND THIS IS BECAUSE WE NEED TO CARRY OVER LINES TO EACH SPLIT FILE
def split_files_by_seq(filepath,num_files_to_make,number_lines_per_seq,contains_header_row):
    """


        This function is used for splitting a single file into multiple little files. This will be useful for multithreading purposes.

        .. note::
            First make sure files do not start with any documentation fields


        =====================   =====================
        **Input**               **Description**
        ---------------------   ---------------------
        filepath                input file
        num_files_to_make       number of split files to create
        number_lines_per_seq    number of lines that correspond to a single sequence (fastq files = 4, fastqfiles =2)
        contains_header_row
        =====================   =====================

        .. important::
             We cannot just use the split command, instead we have to use awk command. This is because we need to carry over lines to each split file.

    """
    #IMPORTANT => FIRST MAKE SURE FILES DO NOT START WITH ANY DOCUMENTATION FIELDS
    num_doc_fields = 0
    #open file and make sure it does not start with documentation
    header_lines = ''

    with open(filepath,'r') as i:
        while True:
            line = i.readline()
            if line.startswith(descriptor_symbol):
                num_doc_fields+=1
                header_lines+=line
            else:
                if contains_header_row:
                    num_doc_fields+=1
                    #NOW read the top header line
                    header_lines+=line
                break


    parent_path = '/'.join(filepath.split('/')[:-1])

    if num_doc_fields>0:
        my_temp_file = parent_path+'/header_rows_'+str(datetime.now()).replace(' ','')
        with open(my_temp_file,'w') as e:
            e.write(header_lines)


    #first get the number of lines in the file
    num_lines = file_line_count(filepath)
    #make sure the number of lines per seq matches what would be expected from num_lines
    if(num_lines%number_lines_per_seq!=0):
        raise Exception('Number of lines in file is not divisible by the number of lines for each sequence: {0}/{1}!=0'.format(str(num_lines),str(number_lines_per_seq)))

    num_seqs = num_lines/number_lines_per_seq
    #determine how many lines to split the file by
    #round down, division THEN add 1
    #we add a 1 to ensure that the num_files_to_make is the max number of files made
    num_lines_in_split_files = (int(num_seqs/num_files_to_make)+1)*number_lines_per_seq

    #make a temp folder
    subfolder = parent_path+'/'+str(datetime.today()).replace(' ','_').replace(':','').replace('.','')
    os.makedirs(subfolder)

    #ok THERE are header lines at the top fo the file that we dont watn to split so we need to ignore these lines
    if num_doc_fields>0:
        #the final '-' is IMPORTANT when combining with tail
        system_command = "tail -n +{5} '{1}'| split -l {0} -a {4} - '{2}/{3}'".format(str(num_lines_in_split_files),filepath,subfolder,os.path.basename(filepath+'.'),num_files_to_make/10+1,num_doc_fields+1)
    else:
        system_command = "split -l {0} -a {4} '{1}' '{2}/{3}'".format(str(num_lines_in_split_files),filepath,subfolder,os.path.basename(filepath+'.'),num_files_to_make/10+1)


    #run the bash split command , split files by lines defined above, generate suffixes whose length is equal to the number of files ot make, output results to temp subfolder, prefix files with inputfile+'.'
    os.system(system_command)

    #return the contents of files made
    files_created = os.listdir(subfolder)



    if num_doc_fields>0:
        #move files back up one folder, but while moving files also concatenate teh header file
        hack_bash_command = '''
            for file in "{0}/"*
            do
                s=$(basename "$file")
                cat "{1}" "$file" > "{2}/$s"
            done
            rm "{1}"
            rm -r "{0}"
        '''.format(subfolder,my_temp_file,parent_path)
        os.system(hack_bash_command)
    else:
        #move files back to starting folder , delete temp folder
        os.system("mv {0}/*.* {1}/.;rm -r {0}".format(subfolder.replace(' ','\ '),parent_path.replace(' ','\ ')))

    return sorted([parent_path+'/'+f for f in files_created])



#runs an awk script for merging results from multiple files
def merge_multiple_files(file_list, num_header_lines=1,outfile=None):
    """
        runs an awk script for merging results from multiple files
    """
    if not outfile: #no outfile, then make default path
        outfile = file_list[0]+'.merged'

    file_list_strings = ' '.join(file_list)#["'"+f+"'" for f in file_list])

    awk ='''
        awk 'FNR!=NR&&FNR<={0}{{next}};
        {{print $0> "{1}" }}' {2}'''.format(str(num_header_lines),outfile,file_list_strings)


    os.system(awk)
    return outfile





#--- The code is included here for prototyping porpoises.
#function deprecated
#def flatten_dictionary_old(d):
#   """Input: a dictionary (only a useful function if it's a nested dictionary).
#   Output: a flattened dictionary, where nested keys are represented in the flat structure with a . separating them.
#   {a: 1, b: {c: 2, d: 3}} --> {a: 1, b.c: 2, b.c: 3}
#   """
#   flattened_dict = {}
#   def _interior_loop(d, parent_key):
#       for key, value in d.items():
#           parent_key = parent_key + [key]
#           if isinstance(value, dict):
#               for item in _interior_loop(value, parent_key[:]):
#                   yield item
#               parent_key.pop()
#           else:
#               yield {'.'.join(parent_key): value}
#               parent_key.pop()

#   for key_value in _interior_loop(d, []):
#       flattened_dict.update(key_value)
#   return flattened_dict

# test=type(ObjectId())
def flatten_dictionary(d,val={},p='',start=True):
    """
        This function flattens dictionaries.
    """
    if start:
        val = {}
    for k,v in d.iteritems():
        if isinstance(v, dict):
            flatten_dictionary(v,val,p+k+'.',False)
        elif isinstance(v,test):
            val[p+k]=str(v)
        else:
            val[p+k] = v
    return val


def RemoveObjId(document):
    """
        Removes ObjectId
    """
    for f,v in document.iteritems():
        if isinstance(v,dict):
            RemoveObjId(v)
        #its an object id
        elif isinstance(v,oid_type):
            document[f]=str(v)
        elif isinstance(v,list) and isinstance(v[0],dict):
            for sub_vals in v:
                if isinstance(sub_vals,dict):
                    RemoveObjId(sub_vals)


#function description - this will extract a specific field from a file and write it to the output file as a  single column (without a header)
#if count_field = None, then we assume there are no counts associated with the field of interest.  if count_field =is not None then we assume that column refers to the number of counts a sequence has occurred
def Write_Single_Field(filename=None,outfile_location=None,field=None,count_field = None, file_format=None,contains_header=True):
    """
        This will extract a specific field from a file and write it to the output file as a single column (without a header.)
        if *count_field* = None, then we assume there are no counts associated with the field of interest.
        If *count_field* =! None, then we assume that column refers to the number of counts a sequence has occurred

    """
    total_data = 0
    total_field = 0

    if outfile_location==None:
        outfile_location = filename+'_singlefield.txt'

    if (filename):
        isfile = os.path.isfile(filename)
    if (filename==None) or (isfile==False):
        raise Exception("The pathname of the file is invalid")
    if(field==None):
        IF_file = readwrite.immunogrepFile(filelocation=filename,filetype='TAB',contains_header=False,mode='r')
        print("Warning no field name was provided.  This file will be treated as a tab file and the first column will be selected")
        field='Column 1'
    else:
        IF_file = readwrite.immunogrepFile(filelocation=filename,filetype=file_format,contains_header=contains_header,mode='r')

        if (file_format==None):
            guessedFiletype = IF_file.getFiletype()
            print("Warning, no file type for this file was provided.  The file was predicted to be a "+guessedFiletype+" file.")
    try:
        outfile = open(outfile_location,'w')
        while not(IF_file.IFclass.eof):
            data = IF_file.IFclass.read() #read in each line as a dictionary
            if data:
                total_data+=1
                if field in data and data[field]:
                    value = data[field]

                    if count_field!=None and count_field in data and data[count_field]:
                        count = data[count_field] #this defines the number of times we will write it to a file
                    else:
                        count = '1'

                    outfile.write(value+'\t'+count+'\n')#write sequence to new file
                    total_field+=1
    except Exception as e:
        os.system("rm '{0}'".format(outfile_location))
        print_error(e)

    return [total_data,total_field]


#Simple python command for counting the occurrences of a sequence ina file.
#assumption 1: sequences are sorted alphabetically
#assumption 2: tab delimited file
#assumption 3: column 1 = sequence of interest, column 2 = counts for that sequence
def count_sorted_seqs(input_file_name, output_file_name):
    """

        Counts the occurances of a sequence in a file. Takes a few assumptions into account.

        :Assumptions: * Sequences are sorted alphabetically
                      * tab delimited file
                      * column 1 = sequence of interest
                      * column 2 = counts for that sequence
    """
    f_in = open(input_file_name,'r')
    f_out = open(output_file_name,'w')

    line_one = f_in.readline().strip()
    line_one = line_one.split('\t')
    current_seq = line_one[0]
    if len(line_one)>1:
        current_count = int(line_one[1])
    else:
        current_count = 1

    for line in f_in:
        data = line.strip()
        data = data.split('\t')
        temp_seq = data[0]
        if len(data)>1:
            temp_count = int(data[1])
        else:
            temp_count = 1

        if (temp_seq == current_seq): #same sequence as before, so keep adding to teh counts
            current_count+=temp_count
        else:
            f_out.write(current_seq+'\t'+str(current_count)+'\n') # new sequence encountered so output results for old sequence and replace new sequence
            current_seq = data[0]
            current_count = temp_count
    f_out.write(current_seq+'\t'+str(current_count)+'\n')
    f_in.close()
    f_out.close()


#filelocation-> location of file
#field -> name of the column/field in the file that you want to read
#file_format -> JSON/TAB/CSV/ETC...
#contains_header -> whether or not the file contains a header row
def count_unique_values(filelocation=None,output_filelocation=None,field=None,count_field=None,file_format=None,contains_header=True,delete_intermediate_file=True,mem_safe = False):
    """
        ===============   ================
        **Input**         **Description**
        ---------------   ----------------
        filelocation      location of file
        field             name of the column/field in the file that you want to read
        file_format       JSON/TAB/CSV/etc.
        contains_header   whether or not the file contains a header row
        ===============   ================
    """
    if output_filelocation == None:
        output_filename = removeFileExtension(filelocation)
        output_filename = output_filename+'.unique_vals.txt'
        unique_counts = output_filename+'.counts'
    else:
        output_filename = output_filelocation+'.single_field_list'
        output_filename2 = output_filelocation+'_temp2'
        unique_counts = output_filelocation

    [total_found,total_field] = Write_Single_Field(filelocation,output_filename,field,count_field, file_format,contains_header) #take the field we are interested in and just write it to a temp file

    if mem_safe:
        #bash_command = '''sort '{0}' | uniq -c | awk 'BEGIN{{OFS="\t"}}{{ print $2,$1,$1 }}' > '{1}' '''.format(output_filename,unique_counts)  --> oldest method, no longer used

        #USE THESE LINES IF WE FIND THAT THERE ARE MEMORY LIMITATIONS/ERRORS WITH THE FUNCTION##
        #print datetime.now()
        bash_command = '''sort '{0}' > '{1}' '''.format(output_filename,output_filename2)
        os.system(bash_command)
        count_sorted_seqs(output_filename2,unique_counts)
        os.system("rm '{0}'".format(output_filename2))
        #print datetime.now()
        ###END OF MEMORY SMART BUT SLOER FUNCTION ################
    else:
        #FAST method, but could have memory limitations for extremely large files)
        bash_command = '''awk '{{OFS = "\t"}} {{arr[$1]+=$2}} END {{for (i in arr) {{print i,arr[i]}}}}' '{0}' > '{1}' '''.format(output_filename,unique_counts)
        os.system(bash_command)

    if delete_intermediate_file:
        os.system("rm '{0}'".format(output_filename))

    #print datetime.now()

    return [total_found,total_field]



try:
    import appsoma_api
except:
    pass
#print an error message if system/program fails
def print_error(e=None):
    """
        Prints an error message if system/program fails.

        exception code::

            if not(e):
                e = "Exception error not passed"
            else:
                appsoma_api.html_append( "<br><font color='red'> there was an error: '{e}' </font>  ".format(e=str(e)))

    """
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    appsoma_api.html_append('<br>')

    if not(e):
        e = "Exception error not passed"
    else:
        appsoma_api.html_append( "<br><font color='red'> there was an error: '{e}' </font>  ".format(e=str(e)))

    appsoma_api.html_append("<br> <font color='red'> Line Number: {0} , type: {1} , fname: {2} </font><br>".format(str(exc_tb.tb_lineno),str(exc_type),str(fname)))
    tb_error = traceback.format_exc()
    appsoma_api.html_append("<font color = 'red'><br> Traceback Error:<br>{error} </font>".format(error = tb_error))
    #for tb in traceback.format_tb(sys.exc_info()[2]):
    #   appsoma_api.html_append("<br> <font color = 'red'>{0}</font>".format(tb))




    appsoma_api.html_append("<br><font color='red'>  Please Restart </font>")
    sys.exit()

# this is a cleanup function to remove any unused fields
# this will iterate the sequence document and remove any subdocuments or fields that have "None" values
def removeEmptyVals(myDict):
    """
        this is a cleanup function to remove any unused fields
        this will iterate the sequence document and remove any subdocuments or fields that have "None" values
    """
    if myDict:
        copyDict = myDict.copy();

        for myKeys in myDict:
            if type(myDict[myKeys]) is dict:
                #if it has a subdocument then recursively remove any None elements in subdocument
                subDict = removeEmptyVals(myDict[myKeys])
                if subDict == {}:
                    copyDict.pop(myKeys,None)
                else:
                    copyDict[myKeys] = subDict;
            else:
                if myDict[myKeys]!=0 and myDict[myKeys]!=False and not myDict[myKeys]:
                    copyDict.pop(myKeys,None)
    else:
        copyDict = myDict

    return copyDict

#ASSUMES THAT THE DICTIONARY IS ONLY IN DOT NOTATION!!! I.E. NOT A NESTED DICTIONARY
# this is a cleanup function to remove any unused fields
# this will iterate the sequence document and remove any subdocuments or fields that have "None" values or empty strings or empty lists
#any fields that are 'empty' are retuend as a second variable
def divideEmptyAndNonEmptyVals(myDict):
    """

        This is a cleanup function that removes any unused fields.
        This will iterate the sequence document and remove any subdocuments or fields that have "None" values, empty strings or empty lists.
        Fields that are empty are returned as a second variable.

        .. note::
            This method assumes that the dictionary is in dot notation. i.e. not a nested dictionary
    """
    empty_fields={}
    non_empty = {}
    for field,value in myDict.iteritems():
        if value!=False and not(value):
            empty_fields[field]= ""
        else:
            non_empty[field] = value

    return [non_empty,empty_fields]

# this is a cleanup function to remove any unused fields
# this will iterate the sequence document and remove any subdocuments or fields that have "None" values
def removeNoneVals(myDict):
    """

        This is a clean up function to remove usued fields
        This will iterate the sequence document and remove any subdocuments or fields that have "None" values
    """
    if myDict:
        copyDict = myDict.copy();

        for myKeys in myDict:
            if type(myDict[myKeys]) is dict:
                #if it has a subdocument then recursively remove any None elements in subdocument
                subDict = removeNoneVals(myDict[myKeys])
                if subDict == {}:
                    copyDict.pop(myKeys,None)
                else:
                    copyDict[myKeys] = subDict;
            else:
                if myDict[myKeys]==None:
                    copyDict.pop(myKeys,None)
    else:
        copyDict = myDict

    return copyDict



#spint out a counter of the current status of a process (i.e. percent done)
def LoopStatus(counter,totalSeq,perIndicate,startPer,div='',addedInfo=None):
    """
        counter of the current status of a process. (i.e. percent done)
    """
    percentDone = int(counter/float(totalSeq)*100)
    if percentDone%perIndicate==0 and percentDone>startPer:
        stringvar ='{0}% percent done. Time: {1}'.format(str(percentDone),str(datetime.now()))
        if addedInfo:
            stringvar+='\n{0}\n\n'.format(addedInfo)
        print(stringvar)
        startPer = percentDone
    return startPer

#spint out a counter of the current status of a process (i.e. percent done)
#THIS FUNCTION USES GENERATOR INSTEAD
def LoopStatusGen(totalSeq,perIndicate,addedInfo=None):
    """
        counter of the current status of a process.

        .. note::
            this function uses generator instead

        .. seealso::
           :py:func:`.LoopStatus`
    """
    counter=0
    startPer = 0
    while True:
        percentDone = int(counter/float(totalSeq)*100)
        if percentDone%perIndicate==0 and percentDone>startPer:
            stringvar ='{0}% percent done. Time: {1}'.format(str(percentDone),str(datetime.now()))
            if addedInfo:
                stringvar+='\n{0}\n\n'.format(addedInfo)

            print(stringvar) #print out the current perecent
            startPer = percentDone
        yield startPer #use a generator to pause
        counter+=1

def removeFileExtension(stringFileName):
    """
        Removes File Extension
    """
    filename = stringFileName.split('.')
    lastExtension = filename[-1]

    foundExtension = False

    for i in listofextension:
        if i==lastExtension:
            foundExtension = True

    if foundExtension:
        editedFileName = filename[0]
        for i in range(1,len(filename)-1):
            editedFileName+="."+filename[i]
    else:
        editedFileName = stringFileName

    return editedFileName


def fieldsForAnnotatingAb():
    """
        Fields in antibody annotations

        =============   =======================
        **abField**     **Comments**
        -------------   -----------------------
        FULL_SEQ        Dna sequence
        SEQ_HEADER      header for the dna sequence
        STRAND_DIR      after the alignment is the v/d/j gene aligned to the fwd or reverse complement
        VGENE_START
        JGENE_START
        FR1_START_NT    nucleotide position along sequence where FR1 starts
        FR1_END_NT
        CDR1_START_NT
        CDR1_END_NT
        FR2_START_NT
        FR2_END_NT
        CDR2_START_NT
        CDR2_END_NT
        CDR3_START_NT
        CDR3_END_NT
        FR4_START_NT
        FR4_END_NT
        SEQ_ALGN        the actual sequence that is aligned to the germline (includes gap characters(-)), to be use for later scripts
        GERMLINE_ALGN   the actual germline sequence that best aligns to sequence (includes gap characters (-)), to be used for later scripts
        START_FEATURE   what region does the antibody start/along alignment
        =============   =======================


    """
    abFields = {
        "FULL_SEQ":None, #dna sequence
        "SEQ_HEADER":None, #header for dna sequence
        "STRAND_DIR":None, #after the alignment is the v/d/j gene aligned to the fwd or reverse complement?
        "VGENE_START":None,
        "JGENE_START":None,
        "FR1_START_NT":None, #nucleotide position along sequence where FR1 starts
        "FR1_END_NT":None,
        "CDR1_START_NT":None,
        "CDR1_END_NT":None,
        "FR2_START_NT":None,
        "FR2_END_NT":None,
        "CDR2_START_NT":None,
        "CDR2_END_NT":None,
        "CDR3_START_NT":None,
        "CDR3_END_NT":None,
        "FR4_START_NT":None,
        "FR4_END_NT":None,
        "SEQ_ALGN":None, #the actual sequence that is aligned to the germline (includes gap characters (-)), to be used for later scripts
        "GERMLINE_ALGN":None, #the actual germline sequence that best aligns to sequence (includes gap characters (-)), to be used for later scripts
        "START_FEATURE":None #what region does the antibody start/along alignment
    };
    return abFields

