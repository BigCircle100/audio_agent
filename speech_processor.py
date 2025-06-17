from funasr import AutoModel
import numpy as np
import soundfile
from funasr.utils.postprocess_utils import rich_transcription_postprocess

# para for test, used in get_chunk func to simulate data source from microphone
CHUNK_SIZE = 200
WAV_FILE = '/home/chenxin/.cache/modelscope/hub/models/iic/speech_fsmn_vad_zh-cn-16k-common-pytorch/example/vad_example.wav'

class SpeechProcessor:
    def __init__(self, mute_time: int = 2000):
        """ Initialization. 
            sample_rate and chunk_size should be obtained from get_chunk

        Args:
            mute_time (int, optional): 
                The duration without human voices. 
                It is also the indicator that the voice command has ended.
                Defaults to 2000(ms).
        """        
        self.vad_model = AutoModel(
            model="fsmn-vad",
            disable_update=True
        )
        self.asr_model = AutoModel(
            model="iic/SenseVoiceSmall",
            disable_update=True,
        )
        self.sample_rate = 44100
        self.chunk_size = 200 
        self.mute_time = mute_time
        

    def get_chunk(self, url: str = None):
        """ Get audio chunk from microphone server.
            Here, local files are used for simulation. 
            chunk_size and sample_rate should be initialized from server message or audio attribute.

        Args:
            url (str, optional): 
                The source of audio chunk. 
                Here is not used. Using local file instead.

        Yields:
            numpy.ndarray: Each audio chunk.
        """        

        self.chunk_size = CHUNK_SIZE
        speech, sample_rate = soundfile.read(WAV_FILE)
        self.sample_rate = sample_rate
        chunk_stride = int(self.chunk_size * sample_rate / 1000)
        total_chunk_num = int(len((speech)-1)/chunk_stride+1)

        for i in range(total_chunk_num):
            speech_chunk = speech[i*chunk_stride:(i+1)*chunk_stride]    
            yield speech_chunk

    def get_instruction_text(self)-> str:
        """ Converting audio stream to the text instruction.
            Using VAD to define the interval with instruction and extract it by ASR.

        Returns:
            str: Text instruction
        """        
        cache = {}
        speech_start = -1
        speech_end = -1
        silence_count = 0           # chunk count without voice
        voice_chunk = np.array([])  # combine the streaming chunk to complete audio
        is_blank = True             # whether the chunk has voice
        for speech_chunk in self.get_chunk():
            vad_res = self.vad_model.generate(input=speech_chunk, cache=cache, is_final=False, chunk_size=self.chunk_size)
            voice_chunk = np.concatenate((voice_chunk, speech_chunk))

            if (len(vad_res[0]["value"])):
                intervals = vad_res[0]["value"]
                
                for interval in intervals:
                    if (interval[0] != -1):
                        is_blank = False
                        if (speech_start == -1):
                            speech_start = interval[0]
                    if (interval[1] != -1):
                        is_blank = True
                        silence_count = 0
                        speech_end = interval[1]
            else:
                # the end of instruction
                if (is_blank):
                    silence_count += 1
                    if (silence_count*self.chunk_size > self.mute_time):
                        voice_chunk = voice_chunk[speech_start: speech_end]
                        break
                    
        asr_res = self.asr_model.generate(
            input=voice_chunk,
            cache={},
            language="auto",  # "zn", "en", "yue", "ja", "ko", "nospeech"
            use_itn=True,
            batch_size_s=60,
        )
        asr_text = rich_transcription_postprocess(asr_res[0]["text"])
        return asr_text


if __name__ == "__main__":
    sp = SpeechProcessor()
    print(sp.get_instruction_text())
            


