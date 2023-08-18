!pip install nltk

#from spellchecker import SpellChecker
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer, PorterStemmer
nltk.download(["punkt","wordnet"])
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import re
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from gensim import corpora
from collections import Counter
from torch.utils.data import DataLoader
from torch.utils.data import TensorDataset


df= pd.read_csv("/content/drive/MyDrive/IMDB Dataset.csv") # specify your own file path  

df["sentiment"]= pd.Series(np.where(df["sentiment"]=="positive",1,0))

# df["sentiment"].value_counts().plot.bar(title= "Sentiment Distribution in the dataset")
# plt.xlabel("Sentiments")
# plt.ylabel("Number of Examples")
# plt.show()

TEXT_CLEANING_RE = "@\S+|https?:\S+|http?:\S+|[^A-Za-z0-9]+"

"""Lowercasing and removing all sorts of punctuations including html tags, urls"""

def clean_text(text):
  text = re.sub(TEXT_CLEANING_RE,' ', str(text).lower()).strip()
  tokens = []
  for token in text.split():
    tokens.append(token)
  return " ".join(tokens)


df["review"]= df["review"].apply(lambda text: clean_text(text))

lemma= WordNetLemmatizer()
def lemmatize_text(text):
  return " ".join([lemma.lemmatize(word) for word in text.split()])


df["lemmatised_text"]= df["review"].apply(lambda text: lemmatize_text(text))

df["lemmatised_text"].head()

# word_tokenize is pre-define function in nltk.tokenize

df["tokenized_text"]=df["lemmatised_text"].apply(lambda text: word_tokenize(text))
df["tokenized_text"]


"""creating vocabulary for index based dictionary mapping of all the words."""

words=[]
for index, row in df[["tokenized_text"]].iterrows():
  for i in range(len(row["tokenized_text"])):
    words.append(row["tokenized_text"][i])
count_words= Counter(words)
sorted_words = sorted(count_words,key=count_words.get,reverse=True)

vocab_to_int={w:i+1 for i,w in enumerate(sorted_words)}

"""Tokenize the reviews to get the final integer mapping."""

review_int=[]
for index,row in df[["tokenized_text"]].iterrows():
  review_int.append([vocab_to_int[x] for x in row["tokenized_text"]])

review_length= [len(i) for i in review_int]
pd.Series(review_length).hist()
plt.show()
pd.Series(review_length).describe()


if torch.cuda.is_available():
  device= torch.device("cuda")
else:
  device= torch.device("cpu")

# print(device)

def make_target(label):
    if label == 1:
        return torch.tensor([1], dtype=torch.long, device=device)
    else:
        return torch.tensor([0], dtype=torch.long, device=device)

df["sentiment"]=df["sentiment"].apply(lambda x: make_target(x))


def padding(sentence,pad_len):
  if len(sentence)<=pad_len:
    sentence=sentence+list(np.zeros(pad_len-len(sentence),dtype=int))
  else:
    sentence=sentence[0:pad_len]
  return sentence

review_int=[padding(x,500) for x in review_int] # Majority of review sentences have more than 500 words

"""Splitting into train and test set."""

# since review_int is a list, we pass the ground truth sentiment score also as a list into train_test_split
X_train, X_test, Y_train, Y_test = train_test_split(review_int,df['sentiment'].values.astype("int64"),shuffle=True,test_size=0.2,random_state=10)


batch_size=32

# creating Tensor Datasets
train_data= TensorDataset(torch.from_numpy(np.array(X_train)),torch.from_numpy(np.array(Y_train)))
test_data= TensorDataset(torch.from_numpy(np.array(X_test)),torch.from_numpy(np.array(Y_test)))

train_loader= DataLoader(train_data,shuffle=True,batch_size=batch_size)
test_loader= DataLoader(test_data,shuffle=True,batch_size=batch_size)

"""Obtaining one batch for manual check:"""

dataiter= iter(train_loader)
sample_x,sample_y=dataiter.next()

print("Sample input:\n",sample_x)
print("\n")
print("Sample label:\n",sample_y)

class GRU_NET(nn.Module):
  def __init__(self,vocab_size,output_size,embedding_size,hidden_dim,n_layer,drop_prob=0.2):
    super(GRU_NET,self).__init__()

    self.output_size=output_size
    self.hidden_dim= hidden_dim
    self.n_layer= n_layer

# For word to vector embedding can use pretrained models like Glove(stanford opensource)
    self.embedding= nn.Embedding(vocab_size,embedding_size) # Have used the untrained embedding neural network
    self.gru= nn.GRU(embedding_size,hidden_dim,n_layers,dropout=drop_prob,batch_first=True)


    #Dropout Layer
    self.dropout= nn.Dropout(drop_prob)

    #Fully connected Layer
    self.fc= nn.Linear(hidden_dim,output_size)
    self.nonlinearity= nn.ReLU()

  def forward(self,x,hidden):
    
    batch_size= x.size(0)
    embeds= self.embedding(x)
    out,hidden= self.gru(embeds,hidden)

    out= self.droput(out)
    out = self.fc(out[:,-1])
    sig_out= self.nonlinearity(out)

    return sig_out,hidden

  
  def init_hidden(self,batch_size):

    weight = next(self.parameters()).data
    hidden = weight.new(self.n_layer, batch_size, self.hidden_dim).zero_().to(device)
        
    return hidden


vocab_size= len(vocab_to_int)+1 # 1 added extra for 0 padding
hidden_dim= 512
output_size=1
n_layer=2
embedding_size=400


model= GRU_NET(vocab_size,output_size,embedding_size,hidden_dim,n_layer)
model.to(device)
print(model)

learning_rate=0.005
loss_function= nn.BCELoss()
optimizer= optim.Adam(model.parameters(), lr=learning_rate)

#training params
epochs = 4
counter=0
print_every=100
clip=5 # gradient clipping

model.train()

for epoch in range(epochs):
  #Initialising the hidden state.
  h= model.init_hidden(batch_size)

  #batch looping
  for inputs, labels in train_loader:
    counter+=1
    h= tuple([m.data for m in h])
    inputs,labels= inputs.to(device), labels.to(device)
    model.zero_grad()
    output, h= model(inputs,h)
    loss= criterion(output.squeeze(),labels.float())
    loss.backward()
    nn.utils.clip_grad_norm_(model.parameters(), clip)
    optimizer.step()
        
    if counter%print_every == 0:
      val_h = model.init_hidden(batch_size)
      val_losses = []
      model.eval()
      for inp, lab in val_loader:
        val_h = tuple([each.data for each in val_h])
        inp, lab = inp.to(device), lab.to(device)
        out, val_h = model(inp, val_h)
        val_loss = criterion(out.squeeze(), lab.float())
        val_losses.append(val_loss.item())
                
       model.train()
       print("Epoch: {}/{}...".format(i+1, epochs),
            "Step: {}...".format(counter),
          "Loss: {:.6f}...".format(loss.item()),
            "Val Loss: {:.6f}".format(np.mean(val_losses)))
         if np.mean(val_losses) <= valid_loss_min:
           torch.save(model.state_dict(), './state_dict.pt')
           print('Validation loss decreased ({:.6f} --> {:.6f}).  Saving model ...'.format(valid_loss_min,np.mean(val_losses)))
             valid_loss_min = np.mean(val_losses)
