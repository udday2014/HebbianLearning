import torch
from sklearn.kernel_approximation import Nystroem

from ... import params as P
from ... import utils
from ..model import Model

# Base class as wrapper for classifiers from scikit learn
class SkClassif(Model):
	# Layer names
	CLF = 'clf'
	CLASS_SCORES = 'class_scores' # Name of the classification output providing the class scores
	
	def __init__(self, config, input_shape=None):
		super(SkClassif, self).__init__(config, input_shape)
		
		self.INPUT_SIZE = utils.shape2size(self.get_input_shape())
		self.NUM_CLASSES = P.GLB_PARAMS[P.KEY_DATASET_METADATA][P.KEY_DS_NUM_CLASSES]
		
		self.NUM_SAMPLES = config.CONFIG_OPTIONS.get(P.KEY_SKCLF_NUM_SAMPLES, config.CONFIG_OPTIONS.get(P.KEY_NUM_TRN_SAMPLES, config.CONFIG_OPTIONS.get(P.KEY_TOT_TRN_SAMPLES, P.GLB_PARAMS[P.KEY_DATASET_METADATA][P.KEY_DS_TRN_SET_SIZE])))
		self.N_COMPONENTS = config.CONFIG_OPTIONS.get(P.KEY_NYSTROEM_N_COMPONENTS, 100)
		self.N_COMPONENTS = min(self.N_COMPONENTS, self.NUM_SAMPLES)
		self.nystroem = Nystroem(n_components=self.N_COMPONENTS)
		self.clf = None
		self.nystroem_fitted = False
		self.clf_fitted = False
		self.X = []
		self.X_transformed = []
		self.y = []
	
	def state_dict(self):
		d = super(SkClassif, self).state_dict()
		d['nystroem'] = self.nystroem
		d['clf'] = self.clf
		d['nystroem_fitted'] = self.nystroem_fitted
		d['clf_fitted'] = self.clf_fitted
		return d
	
	def load_state_dict(self, state_dict, strict = ...):
		self.nystroem = state_dict.pop('nystroem')
		self.clf = state_dict.pop('clf')
		self.nystroem_fitted = state_dict.pop('nystroem_fitted')
		self.clf_fitted = state_dict.pop('clf_fitted')
		super(SkClassif, self).load_state_dict(state_dict, strict)
	
	# Returns classifier predictions for a given x batch
	def compute_output(self, x):
		return utils.dense2onehot(torch.tensor(self.clf.predict(self.nystroem.transform(x.view(x.size(0), -1).tolist())), device=P.DEVICE), self.NUM_CLASSES)
	
	# Here we define the flow of information through the network
	def forward(self, x):
		out = {}
		
		if self.training:
			if not self.clf_fitted:
				# Here we use just the first NUM_SAMPLES samples to do a Nystroem approximation, because they are already
				# a random subset of the dataset. This allows to save memory by avoiding to store the whole dataset.
				if not self.nystroem_fitted:
					self.X += x.view(x.size(0), -1).tolist()
					if len(self.X) >= self.N_COMPONENTS:
						self.X_transformed = self.nystroem.fit_transform(self.X).tolist()
						self.nystroem_fitted = True
						self.X = []
				else: self.X_transformed += self.nystroem.transform(x.view(x.size(0), -1).tolist()).tolist()
				
				# Here we fit the actual classifier
				if len(self.X_transformed) >= self.NUM_SAMPLES:
					self.clf.fit(self.X_transformed, self.y)
					self.clf_fitted = True
					self.X_transformed = []
					self.y = []
		
		clf_out = self.compute_output(x) if self.clf_fitted else torch.rand((x.size(0), self.NUM_CLASSES), device=P.DEVICE)
		out[self.CLF] = clf_out
		out[self.CLASS_SCORES] = {P.KEY_CLASS_SCORES: clf_out}
		return out
	
	def set_teacher_signal(self, y):
		if y is not None and len(self.y) < self.NUM_SAMPLES and self.training and not self.clf_fitted: self.y += y.tolist()
